import importlib
import unittest


class CodedAnnualTitleTests(unittest.TestCase):
    def setUp(self):self.m=importlib.import_module('scripts.complete_asset_expansion_2026_metadata')

    def row(self):
        return {'instrument':'SH600704','title':'600704_物产中大_2025年_年度报告20260427','day':'2026-04-28',
            'classification':'OTHER_ANNUAL_CATEGORY_TITLE_RETAINED','fiscal_year':None,'edition':None}

    def test_literal_code_year_and_filename_date_complete_source_without_changing_publication_clock(self):
        row=self.row();value=self.m.coded_title(row)
        self.assertEqual(value['fiscal_year'],2025);self.assertEqual(value['classification'],'CODED_TITLE_FULL_REPORT_CANDIDATE')
        self.assertIsNone(row['fiscal_year']);self.assertEqual(value['original_row_sha256'],self.m.digest(row))
        self.assertEqual(value['day'],'2026-04-28')

    def test_code_date_or_fiscal_year_contradiction_is_not_accepted(self):
        for title in ('600999_物产中大_2025年_年度报告20260427','600704_物产中大_2025年_年度报告20260429',
                      '600704_物产中大_2026年_年度报告20260427'):
            row={**self.row(),'title':title}
            with self.subTest(title),self.assertRaises(ValueError):self.m.coded_title(row)

    def test_unrelated_notice_is_retained_as_metadata_without_invented_fiscal_year(self):
        self.assertIsNone(self.m.coded_title({**self.row(),'title':'关于年度报告的提示公告'}))


if __name__=='__main__':unittest.main()
