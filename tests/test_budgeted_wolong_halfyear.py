import unittest
try:
    from scripts.capture_budgeted_wolong_halfyear_pre2026 import select_halfyear
except ImportError:
    select_halfyear=None


class BudgetedWolongHalfyearTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(select_halfyear)
        self.row={'code':'600580','day':'2025-08-28','title':'卧龙电驱：2025年半年度报告',
            'announcement_id':'1220000003','pdf_path':'finalpage/2025-08-28/1220000003.PDF'}

    def test_selects_only_unique_original_halfyear_in_registered_publication_window(self):
        self.assertEqual(select_halfyear([self.row,{**self.row,'title':'2025年半年度报告摘要'}]),self.row)
        with self.assertRaises(ValueError):select_halfyear([self.row,self.row])

    def test_rejects_other_security_future_publication_old_report_or_wrong_path(self):
        for change in ({'code':'600001'},{'day':'2026-08-28'},{'day':'2025-09-01'},
            {'title':'2024年半年度报告'},{'title':'2025年半年度报告（更正后）'},
            {'pdf_path':'finalpage/2026-08-28/1220000003.PDF'},{'announcement_id':'../3'}):
            with self.subTest(change=change),self.assertRaises(ValueError):select_halfyear([{**self.row,**change}])
