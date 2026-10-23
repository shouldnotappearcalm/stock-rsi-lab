import importlib.util
from pathlib import Path
import unittest
from tests import test_asset_expansion_tax_source_review as fixture

p=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-23-asset-expansion-tax-source-review-v2.py'
s=importlib.util.spec_from_file_location('asset_tax_review_v2',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class TaxSourceReviewV2Tests(unittest.TestCase):
    def text(self):return fixture.TaxSourceReviewTests().text().replace('A股','Ａ股').replace('—','－')
    def test_original_fullwidth_row_has_same_labelled_facts(self):
        self.assertEqual(m.text_facts(self.text()),m.text_facts(fixture.TaxSourceReviewTests().text()))
    def test_normalizing_glyphs_cannot_recover_wrong_labels_or_dates(self):
        for before,after in [('股权登记日','wrong'),('2026/5/29','2026/5/28'),('0.2股','0.4股')]:
            with self.subTest(before),self.assertRaises(ValueError):m.text_facts(self.text().replace(before,after))

if __name__=='__main__':unittest.main()
