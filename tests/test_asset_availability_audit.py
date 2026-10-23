import copy,importlib.util
from pathlib import Path
import unittest

from stock_rsi import asset_availability as source
from tests.test_asset_availability import case
from tests.test_profitability_availability import document
from tests.test_industry_catalog import bundle


class AssetAvailabilityAuditTests(unittest.TestCase):
    def setUp(self):
        p=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-23-asset-availability-audit.py'
        self.assertTrue(p.exists(),'separate asset availability checker missing')
        spec=importlib.util.spec_from_file_location('separate_asset_availability_qa',p)
        self.qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.qa)
        self.old=document(2024,'2025-04-29','1');self.new=document(2025,'2026-04-29','2')
        self.docs=[self.old,self.new];self.cases={'1':case(self.old),'2':case(self.new)}
        self.catalog=bundle();self.cohort=['SH600001','SH600030','SZ000998'];self.clock='2026-06-01T15:05:00+08:00'
        self.mode='RECONSTRUCTED_PUBLICATION_DAY_END'
        self.view=source.snapshot_availability(self.docs,self.cases.__getitem__,self.catalog,self.cohort,self.clock,mode=self.mode)

    def validate(self,view):
        return self.qa.validate_view(view,self.docs,self.cases,self.catalog,self.cohort,self.clock,self.mode)

    def test_independent_expected_view_agrees_and_retains_all_cohort_members(self):
        self.validate(self.view)
        self.assertEqual(self.qa.expected_view(self.docs,self.cases,self.catalog,self.cohort,self.clock,self.mode),self.view)

    def test_clock_cohort_industry_and_unrequested_amount_are_rejected_without_hash_gate(self):
        for mutate in (lambda v:v.update(as_of='2026-06-02T07:05:00+00:00'),
            lambda v:v['classifications'].pop(),lambda v:v['classifications'][0].update(industry_status='NONFINANCIAL_IN_SOURCE_VINTAGE'),
            lambda v:v['classifications'][-1].update(total_assets_CNY='200.00'),
            lambda v:v.update(investment_factor_admitted=0)):
            broken=copy.deepcopy(self.view);mutate(broken)
            with self.assertRaises(ValueError):self.validate(broken)

    def test_failed_newest_cannot_be_replaced_with_older_supported_edition(self):
        self.cases['2']=case(self.new,'COVER_IDENTITY_UNVERIFIED')
        good=source.snapshot_availability(self.docs,self.cases.__getitem__,self.catalog,self.cohort,self.clock,mode=self.mode)
        self.validate(good)
        with self.assertRaises(ValueError):self.validate(self.view)
        broken=copy.deepcopy(good);broken['classifications'][-1].update(selected_capture_key='1',latest_fiscal_year=2024)
        with self.assertRaises(ValueError):self.validate(broken)

    def test_future_annual_edition_cannot_appear_at_earlier_clock(self):
        self.clock='2026-01-01T15:05:00+08:00'
        with self.assertRaises(ValueError):self.validate(self.view)
        good=source.snapshot_availability(self.docs,self.cases.__getitem__,self.catalog,self.cohort,self.clock,mode=self.mode)
        self.validate(good)


if __name__=='__main__':unittest.main()
