from copy import deepcopy
from datetime import date
from fractions import Fraction
import unittest
from unittest.mock import patch
from stock_rsi import cash_accrual_monthly as m
from stock_rsi import annual_cash_accruals_v2 as cash
from tests.test_annual_cash_accruals import DOC,source


def fixture(count=110):
    docs=[];cases={};ids={}
    for i in range(count):
        d={**DOC,'instrument':f'SH{600001+i}','effective_fiscal_year':2022,'day':'2023-04-27',
           'capture_key':f'test-{i}','announcement_id':str(1000+i)}
        p=[t.replace('2022','YEARPRIOR').replace('2023','2022').replace('YEARPRIOR','2021') for t in source(profit=f'{i}.00')]
        report=cash.make_report(d,cash.parse_report(p,2022));docs.append(d);ids[d['capture_key']]=report['record_id']
        cases[d['capture_key']]={'capture_key':d['capture_key'],'instrument':d['instrument'],'fiscal_year':2022,
                                'publication_day':d['day'],'source_sha256':d['source_sha256'],
                                'status':m.SUPPORTED,'report':report,'investment_factor_admitted':False,'historical_arrival_verified':False}
    return docs,cases,ids


class CashAccrualMonthlyTests(unittest.TestCase):
    def test_visibility_is_checked_before_every_financial_loader(self):
        def poison(k):raise AssertionError('future monetary read')
        self.assertIsNone(m.observation(DOC,poison,{},'2024-04-27T15:05:00+08:00'))
        self.assertIsNone(m.observation(DOC,poison,{},'2025-12-31T15:05:00+08:00',mode=cash.OBSERVED))
        with self.assertRaises(ValueError):m.visible_latest([DOC],[DOC['instrument']],'2026-01-01T15:05:00+08:00')
    def test_current_ni_minus_cfo_uses_mean_same_edition_assets_and_signed_values(self):
        docs,cases,ids=fixture(1);o=m.observation(docs[0],cases.__getitem__,ids,'2023-12-29T15:05:00+08:00')
        self.assertEqual(Fraction(o['score_fraction']),Fraction(-20,150))
        self.assertFalse(o['investment_factor_admitted'])
    def test_latest_unsupported_blocks_old_supported_without_fallback(self):
        docs,cases,ids=fixture(1);d={**docs[0],'day':'2023-06-01','announcement_id':'9999','capture_key':'new'}
        docs.append(d);cases['new']={**cases['test-0'],'capture_key':'new','publication_day':d['day'],
                                     'status':m.FAILURES[0],'report':None};ids['new']=None
        selected,_=m.visible_latest(docs,[d['instrument']],'2023-12-29T15:05:00+08:00')[d['instrument']]
        self.assertEqual(selected,d);self.assertIsNone(m.observation(selected,cases.__getitem__,ids,'2023-12-29T15:05:00+08:00'))
    def test_same_day_different_bytes_are_ambiguous_and_future_edition_is_ignored(self):
        docs,_,_=fixture(1);d=docs[0];other={**d,'source_sha256':'b'*64,'capture_key':'other'}
        self.assertEqual(m.visible_latest([d,other],[d['instrument']],'2023-12-29T15:05:00+08:00')[d['instrument']][1], 'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS')
        future={**other,'day':'2024-04-29'}
        self.assertEqual(m.visible_latest([d,future],[d['instrument']],'2023-12-29T15:05:00+08:00')[d['instrument']][0],d)
        with self.assertRaises(ValueError):m.visible_latest([d,d],[d['instrument']],'2023-12-29T15:05:00+08:00')
    def test_approved_id_rehashed_cell_and_false_assurances_are_rejected(self):
        for kind in ('id','amount','flag'):
            docs,cases,ids=fixture(1);c=cases['test-0']
            if kind=='id':ids['test-0']='b'*64
            if kind=='amount':
                c['report']['parsed']['income']['2022-12-31']['net_profit']['value_CNY']='999.00'
                c['report']['record_id']=cash.v1.digest({k:v for k,v in c['report'].items() if k!='record_id'});ids['test-0']=c['report']['record_id']
            if kind=='flag':c['historical_arrival_verified']=True
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.observation(docs[0],cases.__getitem__,ids,'2023-12-29T15:05:00+08:00')
    def test_known_amendment_blocks_only_from_publication_day_end(self):
        docs,_,_=fixture(1);d=docs[0];a=[{'instrument':d['instrument'],'capture_key':d['capture_key'],
             'publication_day':'2024-04-24','captured_at_utc':'2026-10-23T00:00:00+00:00'}]
        self.assertFalse(m.known_amendment_blocks(d,a,'2024-04-24T15:05:00+08:00'))
        self.assertTrue(m.known_amendment_blocks(d,a,'2024-04-25T15:05:00+08:00'))
    def build(self,missing=0,amendments=(),end='2024-01-31',callback=None):
        docs,cases,ids=fixture();cohort=[d['instrument'] for d in docs]
        class Snapshot:
            calendar=[date.fromisoformat(s) for s in ('2023-12-29','2024-01-02','2024-01-31','2024-02-01','2025-12-31')]
            def value(self,code,field,day):
                if day not in ('2023-12-29','2024-01-31'):raise AssertionError('future quote')
                return None if code in set(cohort[:missing]) else 1.
        catalog={'classifications':[{'instrument':c,'status':'NONFINANCIAL_IN_SOURCE_VINTAGE'} for c in cohort]}
        members={c:[('2020-01-01','2025-12-31')] for c in cohort}
        with patch.object(m,'snapshot_catalog',return_value=catalog):
            return m.build_targets(Snapshot(),members,cohort,docs,cases.__getitem__,ids,{},amendments,end=end,on_formation=callback)
    def test_low_decile_and_nonpromotable_controls_use_prior_close_and95percent(self):
        targets,receipts=self.build();primary=targets[m.PRIMARY]['2024-01-02'];codes=[f'SH{600001+i}' for i in range(11)]
        self.assertEqual(list(primary['weights']),codes);self.assertAlmostEqual(sum(primary['weights'].values()),.95)
        self.assertEqual(receipts[0]['eligible'],110);self.assertEqual(receipts[0]['formation_asof'],'2023-12-29')
        self.assertEqual(len(targets['eligible_equal_weight']['2024-01-02']['weights']),110)
    def test_complete_coverage_failure_receipts_saved_but_no_partial_account_targets_promoted(self):
        saved=[]
        with self.assertRaisesRegex(ValueError,'coverage'):
            self.build(missing=11,end='2024-02-01',callback=lambda d,t,r:saved.append(r))
        self.assertEqual(len(saved),2);self.assertTrue(all(r['eligible']==99 and not r['coverage_pass'] for r in saved))
        self.assertTrue(all(r['selections']=={} for r in saved))

    def test_registered_v3_wrapped_cfo_observation_uses_same_exact_ratio(self):
        from tests.test_annual_cash_accruals_v3 import pages
        from stock_rsi import annual_cash_accruals_v3 as v3
        d=deepcopy(DOC);report=v3.make_report(d,v3.parse_report(pages(),2023))
        case={'capture_key':d['capture_key'],'instrument':d['instrument'],'fiscal_year':2023,'publication_day':d['day'],
              'source_sha256':d['source_sha256'],'status':m.SUPPORTED,'report':report,
              'investment_factor_admitted':False,'historical_arrival_verified':False}
        o=m.observation(d,lambda k:case,{d['capture_key']:report['record_id']},'2024-05-01T15:05:00+08:00')
        self.assertEqual(Fraction(o['score_fraction']),Fraction(-1,6))
