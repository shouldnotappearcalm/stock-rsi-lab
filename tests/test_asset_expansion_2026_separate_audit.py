from datetime import datetime
import importlib.util
from pathlib import Path
import unittest


class Separate2026MetadataAuditTests(unittest.TestCase):
    def setUp(self):
        p=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-22-asset-expansion-2026-metadata-audit.py'
        s=importlib.util.spec_from_file_location('separate_2026_annual_metadata_QA',p)
        self.m=importlib.util.module_from_spec(s);s.loader.exec_module(self.m)

    def row(self,day='2026-04-30',title='公司2025年年度报告（更新前）'):
        return {'secCode':'600001','announcementTime':int(datetime.fromisoformat(day+'T00:00:00+08:00').timestamp()*1000),
            'announcementTitle':title,'announcementId':'123','adjunctUrl':'finalpage/'+day+'/123.PDF'}

    def test_prior_version_and_unknown_cover_year_remain_explicit(self):
        rows,candidates=self.m.normalize('SH600001',{'totalAnnouncement':1,'announcements':[self.row()]})
        self.assertEqual(candidates[0]['classification'],'PRIOR_VERSION_FULL_REPORT_CANDIDATE')
        rows,candidates=self.m.normalize('SH600001',{'totalAnnouncement':1,'announcements':[self.row(title='年报全文')]})
        self.assertIsNone(candidates[0]['fiscal_year'])

    def test_bad_count_future_publication_or_unsafe_path_cannot_pass_separate_QA(self):
        unsafe=self.row();unsafe['adjunctUrl']='../2027.pdf'
        for value in ({'totalAnnouncement':True,'announcements':[]},
                      {'totalAnnouncement':1,'announcements':[self.row(day='2026-10-22')]},
                      {'totalAnnouncement':1,'announcements':[unsafe]},
                      {'totalAnnouncement':0,'announcements':''}):
            with self.subTest(value),self.assertRaises(ValueError):self.m.normalize('SH600001',value)


if __name__=='__main__':unittest.main()
