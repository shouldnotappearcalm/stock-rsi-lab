import copy
import unittest
try:
    from scripts import audit_operating_pre2026 as audit
except ImportError:
    audit=None
from tests.test_operating_factor import source_case
from stock_rsi.data import digest


class OperatingDevelopmentAuditTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(audit,'separate operating development checker missing')

    def test_independent_signed_source_ratio_for_both_contracts(self):
        for legacy in (False,True):
            d,c,o,a=source_case(legacy=legacy);s=audit.source_score(d,c,o['operating_report'] if o else None,a[d['capture_key']],'2023-12-29T15:05:00+08:00')
            self.assertEqual(s['score_fraction'],'7/20');self.assertEqual(s['operating_profit_CNY'],'35.00');self.assertEqual(s['research_expenses_CNY'],'7.00')

    def test_rehashed_record_unit_date_origin_and_assurance_forgeries_fail(self):
        for mode in ('unit','date','origin','flag','approved'):
            d,c,o,a=source_case();r=c['source_record']
            if mode=='unit':r['payload']['income']['2022-12-31']['revenue'].update(unit='万元',value_CNY='1000000.00')
            elif mode=='date':r['payload']['asset_bridge']['prior']['fiscal_end']='2020-12-31'
            elif mode=='origin':r['payload']['income_origin']='PARENT'
            elif mode=='flag':r['historical_arrival_verified']=True
            r['record_id']=digest({k:v for k,v in r.items() if k!='record_id'});c['effective_record_id']=r['record_id']
            expected='f'*64 if mode=='approved' else r['record_id']
            with self.subTest(mode=mode),self.assertRaises(ValueError):audit.source_score(d,c,None,expected,'2023-12-29T15:05:00+08:00')

    def test_independent_source_units_include_original_CNY_declaration_forms(self):
        for literal in ('单位：元 币种：人民币','单位：人民币元','（金额单位均为人民币元）','单位：元'):
            with self.subTest(literal=literal):self.assertEqual(audit.cny({'literal':'100.00','unit':'元','value_CNY':'100.00','unit_evidence_literal':literal}),100)

    def intents_fixture(self):
        class Quotes:
            def value(self,code,field,day,*,as_of):
                if day!=as_of or day!='2023-12-29':raise AssertionError('future decision quote')
                return 1.
        targets={'2024-01-02':{'as_of':'2023-12-29','weights':{'SH600001':.95}}}
        intent={'execution_session':'2024-01-02','as_of_close_convention':'2023-12-29T15:05:00+08:00','equity_at_decision':1000000.,
            'holdings_at_decision':{},'target_weights':{'SH600001':.95},'latest_decision_price_read':'2023-12-29','execution_exchange_queried_for_decision':False,
            'orders':[{'instrument':'SH600001','side':'BUY','normalized_units':950000.,'known_normalized_close':1.,'known_factor':1.,'as_of':'2023-12-29','quantity_basis':'PRIOR_CLOSE_TARGET'}]}
        orders=[{'session':'2024-01-02','instrument':'SH600001','side':'BUY','requested_normalized_units':'950000.0'}]
        return targets,[intent],[],[],orders,Quotes()

    def test_intents_link_frozen_target_prior_account_and_submitted_quantities(self):
        f=self.intents_fixture();self.assertEqual(audit.audit_intents(*f)['intents_checked'],1)
        for mode in ('target','equity','order','future','submitted'):
            f=self.intents_fixture();i=f[1][0]
            if mode=='target':i['target_weights']['SH600001']=.5
            elif mode=='equity':i['equity_at_decision']=2000000.
            elif mode=='order':i['orders'][0]['normalized_units']=949900.
            elif mode=='future':i['latest_decision_price_read']='2024-01-02'
            else:f[4][0]['requested_normalized_units']='949900'
            with self.subTest(mode=mode),self.assertRaises(ValueError):audit.audit_intents(*f)
