import copy
import importlib
import unittest


class Asset2026PDFResourcesTests(unittest.TestCase):
    def setUp(self):self.m=importlib.import_module('scripts.capture_asset_expansion_2026_annual_pdfs')

    def row(self,aid='123',day='2026-04-28'):
        return {'instrument':'SH600704','announcement_id':aid,'day':day,'fiscal_year':2025,
            'classification':'FULL_ANNUAL_REPORT_CANDIDATE','pdf_path':'finalpage/'+day+'/'+aid+'.PDF'}

    def test_every_initial_and_revised_edition_is_kept_with_unverified_metadata_year(self):
        cases={'SH600704':{'status':'METADATA_CAPTURED_WITH_CANDIDATES','full_report_candidates':[
            self.row(),{**self.row('124','2026-06-01'),'classification':'REVISED_FULL_REPORT_CANDIDATE'}]}}
        before=copy.deepcopy(cases);docs,resources=self.m.specifications(cases)
        self.assertEqual(len(docs),2);self.assertEqual(len(resources),2);self.assertEqual(cases,before)
        self.assertTrue(all(d['cover_fiscal_identity_verified'] is False for d in docs))
        self.assertEqual(resources['SH600704-123']['url'],'https://static.cninfo.com.cn/finalpage/2026-04-28/123.PDF')
        unknown={**self.row(),'fiscal_year':None,'classification':'UNSPECIFIED_YEAR_COVER_REVIEW_CANDIDATE'}
        docs,_=self.m.specifications({'SH600704':{'status':'METADATA_CAPTURED_WITH_CANDIDATES','full_report_candidates':[unknown]}})
        self.assertIsNone(docs[0]['metadata_fiscal_year']);self.assertFalse(docs[0]['cover_fiscal_identity_verified'])

    def test_future_metadata_duplicate_or_wrong_original_identity_fail_before_fetch(self):
        for row in ({**self.row(),'day':'2026-10-22'},{**self.row(),'instrument':'SH600118'},
                    {**self.row(),'pdf_path':'../outside.PDF'},{**self.row(),'fiscal_year':2026}):
            cases={'SH600704':{'status':'METADATA_CAPTURED_WITH_CANDIDATES','full_report_candidates':[row]}}
            with self.subTest(row),self.assertRaises(ValueError):self.m.specifications(cases)
        cases={'SH600704':{'status':'METADATA_CAPTURED_WITH_CANDIDATES','full_report_candidates':[self.row(),self.row()]}}
        with self.assertRaises(ValueError):self.m.specifications(cases)
        with self.assertRaises(ValueError):self.m.specifications({'SH600704':{'status':'METADATA_SOURCE_REJECTED'}})


if __name__=='__main__':unittest.main()
