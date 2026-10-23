from copy import deepcopy
from fractions import Fraction
import unittest
from stock_rsi.data import digest
try:from stock_rsi import operating_amendments as amendment
except ImportError:amendment=None


def fixture():
    obs={'instrument':'SZ002092','capture_key':'old','record_id':'a'*64,'source_sha256':'b'*64,'current_fiscal_end':'2022-12-31','prior_asset_fiscal_end':'2021-12-31','publication_day':'2023-03-31','operating_profit_CNY':'20.00','lagged_assets_CNY':'100.00','score_fraction':'1/5'}
    proof={'contract':'KNOWN_PRIMARY_OPERATING_ASSET_AMENDMENT_V1','instrument':'SZ002092','capture_key':'old','original_record_id':'a'*64,'original_source_sha256':'b'*64,'current_fiscal_end':'2022-12-31','prior_asset_fiscal_end':'2021-12-31','publication_day':'2024-04-24','documents':[{'sha256':'c'*64,'pages':[1,3,7,19]},{'sha256':'d'*64,'pages':[1,3,7,19]}],'before_assets_CNY':'100.00','after_assets_CNY':'125.00','unchanged_numerator_CNY':'20.00','revenue_delta_CNY':'-5.00','cost_delta_CNY':'-5.00','selling_admin_unchanged':True}
    meta={k:proof[k] for k in ('instrument','capture_key','original_record_id','current_fiscal_end','prior_asset_fiscal_end','publication_day')};meta.update(key='proof',captured_at_utc='2026-10-23T00:00:00+00:00',payload_digest=digest(proof))
    return obs,proof,[meta]

class KnownAmendmentTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(amendment,'known amendment adapter missing')
    def test_future_and_observed_mode_never_read_payload(self):
        obs,proof,meta=fixture()
        for at,mode in [('2024-04-24T15:05:00+08:00','RECONSTRUCTED_PUBLICATION_DAY_END'),('2024-04-25T15:05:00+08:00','OBSERVED_ARRIVAL')]:
            seen=[]
            def load(k):seen.append(k);raise AssertionError('future monetary payload touched')
            v,rs=amendment.apply_known_amendments(obs,at,meta,load,mode);self.assertEqual(v,obs);self.assertEqual(rs,[]);self.assertEqual(seen,[])
    def test_visible_patch_corrects_fraction_and_retains_original(self):
        obs,proof,meta=fixture();before=deepcopy(obs)
        v,rs=amendment.apply_known_amendments(obs,'2024-04-30T15:05:00+08:00',meta,lambda k:proof,'RECONSTRUCTED_PUBLICATION_DAY_END')
        self.assertEqual(Fraction(v['score_fraction']),Fraction(4,25));self.assertEqual(v['lagged_assets_CNY'],'125.00');self.assertEqual(v['original_record_id'],obs['record_id']);self.assertEqual(v['publication_day'],'2024-04-24');self.assertEqual(obs,before);self.assertEqual(len(rs),1)
    def test_later_year_does_not_load_older_patch(self):
        obs,proof,meta=fixture();obs.update(current_fiscal_end='2023-12-31',prior_asset_fiscal_end='2022-12-31',capture_key='new')
        v,rs=amendment.apply_known_amendments(obs,'2024-05-31T15:05:00+08:00',meta,lambda k:self.fail('older patch loaded'),'RECONSTRUCTED_PUBLICATION_DAY_END');self.assertEqual(v,obs);self.assertEqual(rs,[])
    def test_changed_identity_payload_or_economics_rejected(self):
        for field,value in [('original_record_id','e'*64),('before_assets_CNY','99.00'),('revenue_delta_CNY','-6.00'),('selling_admin_unchanged',False),('after_assets_CNY','NaN')]:
            obs,p,meta=fixture();p[field]=value;meta[0]['payload_digest']=digest(p)
            with self.subTest(field=field),self.assertRaises(ValueError):amendment.apply_known_amendments(obs,'2024-04-30T15:05:00+08:00',meta,lambda k:p,'RECONSTRUCTED_PUBLICATION_DAY_END')
        obs,p,meta=fixture();p['after_assets_CNY']='150.00'
        with self.assertRaises(ValueError):amendment.apply_known_amendments(obs,'2024-04-30T15:05:00+08:00',meta,lambda k:p,'RECONSTRUCTED_PUBLICATION_DAY_END')
    def test_naive_time_and_unknown_mode_fail_before_loader(self):
        obs,p,meta=fixture()
        for at,mode in [('2024-04-30T15:05:00','RECONSTRUCTED_PUBLICATION_DAY_END'),('2024-04-30T15:05:00+08:00','GUESS')]:
            with self.assertRaises(ValueError):amendment.apply_known_amendments(obs,at,meta,lambda k:self.fail('loaded'),mode)
    def test_reform_reconstructs_original_selection_and_refuses_corrupt_receipt(self):
        obs,p,meta=fixture();rows={}
        for i in range(10):
            v=deepcopy(obs);v.update(instrument='SZ'+str(i).zfill(6),capture_key=str(i),score_fraction=str(i+1),operating_profit_CNY=str((i+1)*100));rows[v['instrument']]=v
        r={'formation_asof':'2024-04-30','execution_session':'2024-05-06','ranked_source':rows,'selections':{'operating_profit_prior_assets_top_decile_conditional':['SZ000009'],'operating_profit_prior_assets_bottom_decile_control':['SZ000000'],'eligible_equal_weight':sorted(rows)}}
        targets,rs=amendment.reform_receipts([r],[],lambda k:self.fail('unused'),'RECONSTRUCTED_PUBLICATION_DAY_END')
        self.assertEqual(targets['operating_profit_prior_assets_bottom_decile_control']['2024-05-06']['weights'],{'SZ000000':.95});self.assertEqual(rs[0]['known_amendment_receipts'],[])
        r['selections']['operating_profit_prior_assets_bottom_decile_control']=['SZ000001']
        with self.assertRaises(ValueError):amendment.reform_receipts([r],[],lambda k:None,'RECONSTRUCTED_PUBLICATION_DAY_END')
