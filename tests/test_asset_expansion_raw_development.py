import copy
import importlib
import unittest


class AssetRawDevelopmentTests(unittest.TestCase):
    def setUp(self):self.m=importlib.import_module('scripts.run_asset_expansion_raw_development')

    def packet(self):
        return {'instrument':'SH600535','bars':[{'date':'2025-03-26','close':'14.78'},
            {'date':'2025-03-27','preclose':'14.78'}],
            'distributions':[{'dividOperateDate':'2025-03-26'}],
            'adjustments':[{'dividOperateDate':'2025-03-26','foreAdjustFactor':'.96','backAdjustFactor':'10.3','adjustFactor':'1'},
                {'dividOperateDate':'2025-03-27','foreAdjustFactor':'.96','backAdjustFactor':'10.3','adjustFactor':'10.3'}]}

    def test_relationship_is_evidence_only_and_never_mutates_source(self):
        p=self.packet();before=copy.deepcopy(p);r=self.m.restoration_receipts(p)
        self.assertEqual(len(r),1);self.assertEqual(r[0]['distribution_day'],'2025-03-26');self.assertEqual(p,before)

    def test_new_factor_or_raw_reference_gap_cannot_be_waived_as_restoration(self):
        for field,value in [('foreAdjustFactor','.97'),('backAdjustFactor','11'),('adjustFactor','1')]:
            p=self.packet();p['adjustments'][1][field]=value
            with self.subTest(field),self.assertRaises(ValueError):self.m.restoration_receipts(p)
        p=self.packet();p['bars'][1]['preclose']='14.50'
        with self.assertRaises(ValueError):self.m.restoration_receipts(p)
        p=self.packet();p['distributions']=[]
        with self.assertRaises(ValueError):self.m.restoration_receipts(p)

    def result(self):
        return {'status':'RAW_DAILY_PROXY_RECONCILED','2024_return_pct':1.,'2025_return_pct':2.,
            'average_exposure_pct':93.,'account_sessions':485,'monthly_decisions':24,
            'whole_day_volume_violations':0,'all_fills_integer':True,'daily_cash_and_share_conservation':True,
            'record_date_entitlements_verified':True,'unverified_noncash_zero_ownership_verified':True}

    def test_only_complete40bp_physical_account_can_pass(self):
        self.assertTrue(self.m.development_gate({'20':{'status':'INVALID'},'40':self.result()}))
        for key,value in [('2024_return_pct',0.),('2025_return_pct',float('nan')),('average_exposure_pct',89.),
                          ('account_sessions',484),('monthly_decisions',23),('whole_day_volume_violations',1),
                          ('all_fills_integer','true'),('unverified_noncash_zero_ownership_verified',False)]:
            r=self.result();r[key]=value
            with self.subTest(key):self.assertFalse(self.m.development_gate({'20':self.result(),'40':r}))
        self.assertFalse(self.m.development_gate({'20':self.result()}))


if __name__=='__main__':unittest.main()
