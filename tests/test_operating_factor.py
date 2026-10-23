import copy
from fractions import Fraction
import unittest

try:
    from stock_rsi import operating_factor as factor
except ImportError:
    factor=None
from stock_rsi import annual_operating as op, operating_source_bridge as bridge
from stock_rsi.data import digest
from tests.test_annual_operating import source
from tests.test_operating_source_bridge import synthetic_inputs
from tests.test_profitability_availability import document


def source_case(index=0,*,legacy=False,revenue=None):
    doc=document(2022,'2023-04-29',str(index+1));doc['instrument']=f'SZ000{index+100:03}'
    texts=source(2022,cost='60.00',admin='-5.00')
    texts[2]=texts[2].replace('其中：营业收入 七、61 100.00',f'其中：营业收入 七、61 {100+index if revenue is None else revenue}.00')
    texts.append('主要会计数据和财务指标\n2022年末 2021年末 2020年末\n总资产（元） 200.00 100.00 80.00\n')
    _,_,pages,_=synthetic_inputs()
    for p in pages:
        for w in p['words']:
            if w['text'] in ('2023年末','2022年末','2021年末'):w['text']=f'{int(w["text"][:4])-1}年末'
    cell=op.grammar.parse_consolidated_tables(texts,2022)['2022-12-31']['total_assets']
    report=op.make_report(doc['instrument'],2022,doc['day'],doc['captured_at_utc'],doc['source_sha256'],doc['announcement_id'],op.parse_report(texts,2022)) if legacy else bridge.recover_source_record(doc,texts,pages,cell,normative_basis=bridge.geometry.basis())
    case={'capture_key':doc['capture_key'],'instrument':doc['instrument'],'fiscal_year':2022,'source_sha256':doc['source_sha256'],
        'effective_source_status':bridge.LEGACY_SUPPORTED if legacy else bridge.SUPPORTED,'effective_record_id':report['record_id'],
        'source_record':None if legacy else report,'asset_bridge':None if legacy else copy.deepcopy(report['payload']['asset_bridge']),
        'historical_arrival_verified':False,'investment_factor_admitted':False}
    old={'capture_key':doc['capture_key'],'instrument':doc['instrument'],'fiscal_year':2022,'source_sha256':doc['source_sha256'],
         'status':'OPERATING_CELLS_SUPPORTED_PENDING_SOURCE_QA','operating_report':report} if legacy else None
    return doc,case,old,{doc['capture_key']:report['record_id']}


class OperatingFactorTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(factor,'approved operating-factor consumer missing')

    def consume(self,f,**kwargs):
        d,c,old,ids=f
        return factor.source_observation(d,lambda k:c,lambda k:old,ids,'2023-12-29T15:05:00+08:00',mode=op.RECONSTRUCTED,**kwargs)

    def test_both_source_contracts_preserve_signed_profit_RnD_and_exact_prior_asset_ratio(self):
        for legacy in (False,True):
            o=self.consume(source_case(legacy=legacy))
            with self.subTest(legacy=legacy):
                self.assertEqual(o['score_fraction'],'7/20');self.assertEqual(o['operating_profit_CNY'],'35.00')
                self.assertEqual(o['lagged_assets_CNY'],'100.00');self.assertEqual(o['research_expenses_CNY'],'7.00')
                self.assertEqual(o['current_fiscal_end'],'2022-12-31');self.assertEqual(o['prior_asset_fiscal_end'],'2021-12-31')
                self.assertFalse(o['historical_arrival_verified']);self.assertFalse(o['investment_factor_admitted'])
        self.assertEqual(self.consume(source_case(revenue=5))['score_fraction'],'-3/5')

    def test_observed_and_future_documents_do_not_read_registry_case_or_payload(self):
        def trap(*a):raise AssertionError('hidden future payload read')
        class Registry:
            def __getitem__(self,k):raise AssertionError('hidden future registry read')
        d=source_case()[0]
        self.assertIsNone(factor.source_observation(d,trap,trap,Registry(),'2023-12-29T15:05:00+08:00'))
        d.update(day='2025-04-29',instrument=object(),source_sha256=object())
        self.assertIsNone(factor.source_observation(d,trap,trap,Registry(),'2023-12-29T15:05:00+08:00',mode=op.RECONSTRUCTED))

    def test_missing_asset_changed_id_source_and_unproven_flags_fail_even_if_rehashed(self):
        for mode in ('null_asset','unit','date','scope','id','source','arrival','comparability'):
            f=source_case();d,c,old,ids=f;r=c['source_record']
            if mode=='null_asset':c['asset_bridge']=r['payload']['asset_bridge']=None
            elif mode=='unit':r['payload']['income']['2022-12-31']['revenue'].update(unit='万元',value_CNY='1000000.00',multiplier_CNY='10000')
            elif mode=='date':r['payload']['asset_bridge']['prior']['fiscal_end']='2020-12-31'
            elif mode=='scope':r['payload']['income_origin']='PARENT'
            elif mode=='source':d['source_sha256']='b'*64
            elif mode=='arrival':r['historical_arrival_verified']=True
            elif mode=='comparability':r['financial_cross_issuer_comparability_verified']=True
            else:ids[d['capture_key']]='f'*64
            if mode!='id':
                r['record_id']=digest({k:v for k,v in r.items() if k!='record_id'});c['effective_record_id']=r['record_id']
                # Also reapprove malicious contents: semantic validation must still reject.
                ids[d['capture_key']]=r['record_id']
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.consume(f)

    def test_legacy_record_cannot_borrow_current_asset_denominator_or_other_edition(self):
        for mode in ('id','clock','fiscal'):
            f=source_case(legacy=True);r=f[2]['operating_report']
            if mode=='id':r['payload']['announcement_id']='999'
            elif mode=='clock':r['publication_day']='2023-05-01'
            else:r['payload']['parsed']['balances']['2021-12-31']['fiscal_end']='2022-12-31'
            r['record_id']=digest({k:v for k,v in r.items() if k!='record_id'});f[1]['effective_record_id']=r['record_id'];f[3][f[0]['capture_key']]=r['record_id']
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.consume(f)

    def test_unsupported_latest_record_cannot_supply_older_numeric_source(self):
        f=source_case();f[1].update(effective_source_status=bridge.STILL_UNSUPPORTED,effective_record_id=None,source_record=None,asset_bridge=None);f[3][f[0]['capture_key']]=None
        self.assertIsNone(self.consume(f))
