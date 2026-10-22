import importlib
import unittest


class AssetPrimaryCaptureTests(unittest.TestCase):
    def setUp(self):self.m=importlib.import_module('scripts.capture_asset_expansion_primary_pre2026')

    def test_exact_original_notice_is_selected_without_preview_or_correction(self):
        row={'code':'600535','day':'2025-03-20','title':'天士力2024年年度权益分派实施公告',
             'announcement_id':'123','pdf_path':'finalpage/2025-03-20/123.PDF'}
        self.assertEqual(self.m.select_implementation_notice([row],self.m.CASES[0]),row)
        for changed in ({**row,'day':'2026-03-20'},{**row,'code':'600737'},
                        {**row,'title':'天士力2024年年度权益分派实施公告更正'},
                        {**row,'pdf_path':'finalpage/2025-03-20/999.PDF'}):
            with self.subTest(changed),self.assertRaises(ValueError):self.m.select_implementation_notice([changed],self.m.CASES[0])

    def test_ambiguous_notice_or_count_truncation_fails_closed(self):
        row={'code':'600737','day':'2025-08-05','title':'中粮糖业2024年末期权益分派实施公告',
             'announcement_id':'123','pdf_path':'finalpage/2025-08-05/123.PDF'}
        with self.assertRaises(ValueError):self.m.select_implementation_notice([row,row],self.m.CASES[1])
        with self.assertRaises(ValueError):self.m.validate_listing({'totalAnnouncement':31,'announcements':[]},self.m.CASES[1],1,None)


if __name__=='__main__':unittest.main()
