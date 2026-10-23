import copy
import unittest
try:
    from scripts import audit_low_operating_raw_pre2026 as audit
except ImportError:
    audit=None
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,DIVIDEND_FIELDS


class LowOperatingRawAuditTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(audit,'separate low operating raw source checker missing')
    def packet(self):
        row=dict(zip(BAR_FIELDS,['2023-12-29','sz.002326','10','11','9','10','10','1000','10000','3','1','0']))
        return {'instrument':'SZ002326','window':['2023-12-29','2025-12-31'],'bars':[row],'distributions':[],'adjustments':[],'quarantine':[]}

    def test_every_ST_suspension_noncash_and_quarantine_is_preserved_as_risk(self):
        p=self.packet();p['bars'][0].update(tradestatus='0',isST='1',volume='0')
        d=dict.fromkeys(DIVIDEND_FIELDS,'');d.update(code='sz.002326',dividOperateDate='2024-05-10',dividStocksPs='0.1',dividCashPsBeforeTax='0.2',dividReserveToStockPs='0')
        p['distributions']=[d];p['quarantine']=[{'reason':'MISSING_OPERATE_DATE','record':{}}]
        r=audit.packet_risks(p,'SZ002326',['2023-12-29'])
        self.assertEqual(len(r['nonordinary_or_suspended_source_rows']),1);self.assertEqual(r['noncash_distributions_requiring_primary_review'],[d]);self.assertEqual(r['quarantines'],p['quarantine'])
        self.assertFalse(r['physical_account_admitted'])

    def test_future_or_wrong_identity_missing_calendar_and_invalid_price_rejected(self):
        for mode in ('future','identity','calendar','price'):
            p=self.packet()
            if mode=='future':p['bars'][0]['date']='2026-01-05'
            elif mode=='identity':p['bars'][0]['code']='sh.600001'
            elif mode=='calendar':p['bars']=[]
            else:p['bars'][0]['close']='NaN'
            with self.subTest(mode=mode),self.assertRaises(ValueError):audit.packet_risks(p,'SZ002326',['2023-12-29'])

    def test_rehashed_sdk_envelope_with_wrong_operation_year_is_rejected(self):
        fields=['code','dividOperateDate'];payload={'fields':['provider_response'],'rows':[{'initial_error_code':'0','final_error_code':'0','iteration_error_type':None,'iteration_error':None,
            'fields':fields,'rows':[['sz.002326','2026-01-05']]}]}
        with self.assertRaises(ValueError):audit.check_component(payload,fields,year=2025)

    def test_quarantine_future_metadata_is_retained_as_failure_not_allowed_source(self):
        p=self.packet();p['quarantine']=[{'reason':'MISSING_OPERATE_DATE','record':{'dividPlanDate':'2026-01-05'}}]
        with self.assertRaises(ValueError):audit.packet_risks(p,'SZ002326',['2023-12-29'])
