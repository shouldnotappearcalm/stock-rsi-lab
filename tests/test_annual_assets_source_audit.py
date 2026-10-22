import importlib.util
from pathlib import Path
import unittest


SCRIPT=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-22-annual-assets-source-audit.py'


class AssetSourceAuditSectionTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('separate_asset_source_qa',SCRIPT)
        self.qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.qa)
        self.lines=[(96,'二、财务报表'),(97,'合并资产负债表'),(98,'母公司资产负债表'),
                    (117,'财务报表附注'),(117,'2022 年度'),(117,'财务报表附注')]
        self.context={'kind':'PRIMARY_FINANCIAL_STATEMENTS_SECTION','start_page':96,'end_page_exclusive':117,
                      'start_literal':'二、财务报表','end_literal':'财务报表附注'}

    def test_repeated_notes_heading_after_first_boundary_does_not_extend_or_invalidate_statement_section(self):
        selected=self.qa.section_segment(self.lines,self.context)
        self.assertEqual(selected,[(96,'二、财务报表'),(97,'合并资产负债表'),(98,'母公司资产负债表')])

    def test_fake_later_end_cannot_skip_an_earlier_notes_or_company_boundary(self):
        lines=[*self.lines[:3],(110,'三、公司基本情况'),*self.lines[3:]]
        with self.assertRaises(AssertionError):self.qa.section_segment(lines,self.context)
        with self.assertRaises(AssertionError):self.qa.section_segment([*self.lines,(118,'二、财务报表')],self.context)
        with self.assertRaises(AssertionError):self.qa.section_segment(self.lines[:3],self.context)


if __name__=='__main__':unittest.main()
