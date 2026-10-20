import copy
import unittest
from scripts.prepare_illiquidity_account_events import classify_source_coverage
from stock_rsi.calendar import TradingCalendar


class DistributionSourceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.calendar=TradingCalendar(['2024-02-29','2024-03-01','2024-03-04'])
        self.bars=[{'date':day,'preclose':'10','close':'10'} for day in ['2024-03-01','2024-03-04']]
        self.adjustment={'dividOperateDate':'2024-03-01','foreAdjustFactor':'.964021',
            'backAdjustFactor':'1','adjustFactor':'1'}
        self.packets={'SH603341':{'bars':self.bars,'distributions':[],'adjustments':[self.adjustment],'quarantine':[]}}
        self.proof={'supplementary_distributions':[],'lifecycles':{'SH603341':{
            'kind':'LISTING_BEGIN','effective_date':'2024-03-01','verified_primary_boundary':True,
            'primary_document_sha256':'a'*64}}}

    def test_initial_forward_normalization_does_not_become_income_or_rewrite_source(self):
        original=copy.deepcopy(self.packets)
        initial,intervals=classify_source_coverage(self.packets,self.proof,self.calendar)
        self.assertEqual(self.packets,original);self.assertEqual(len(initial),1)
        self.assertFalse(initial[0]['factor_used_to_infer_cash_or_shares'])
        self.assertEqual(initial[0]['source_adjustment']['foreAdjustFactor'],'.964021')
        self.assertEqual(len(intervals),1);self.assertEqual(intervals[0]['session'],'2024-02-29')
        self.assertFalse(intervals[0]['synthetic_price_created'])

    def test_changed_initial_or_unexplained_later_adjustment_cannot_hide_in_listing_exception(self):
        original=copy.deepcopy(self.packets)
        for field,value in [('backAdjustFactor','.8'),('adjustFactor','1.1'),('foreAdjustFactor','0')]:
            self.packets=copy.deepcopy(original);self.packets['SH603341']['adjustments'][0][field]=value
            with self.assertRaises(ValueError):classify_source_coverage(self.packets,self.proof,self.calendar)
        self.packets=copy.deepcopy(original)
        self.packets['SH603341']['adjustments'].append({**self.adjustment,'dividOperateDate':'2024-03-04'})
        with self.assertRaises(ValueError):classify_source_coverage(self.packets,self.proof,self.calendar)
        self.packets=copy.deepcopy(original);self.packets['SH603341']['bars'][1]['preclose']='9'
        with self.assertRaises(ValueError):classify_source_coverage(self.packets,self.proof,self.calendar)
