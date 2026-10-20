import copy,hashlib,json,tempfile,unittest
from datetime import date
from pathlib import Path
from scripts.tdx_history_checks import minute_labels
try:
    from scripts.run_low_beta60_intraday_development import CompletePrefixTapeBank,confirmation_passes
except ImportError:
    CompletePrefixTapeBank=confirmation_passes=None


class LowBeta60IntradayTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(CompletePrefixTapeBank);self.assertIsNotNone(confirmation_passes)
    def fixture(self,root):
        c='SH600008';d='2024-01-02';root.mkdir();(root/'sessions').mkdir()
        (root/'plan.json').write_text(json.dumps({'fixture':'synthetic'})+'\n')
        payload={'exchange':'sh','market_id':1,'code':'600008','trading_date':d,
            'points':[{'index':i,'time_label':s,'time':d+'T'+s+':00+08:00','price_milli':10000,'price':10,'volume':2}
                for i,s in enumerate(minute_labels())]}
        p=root/'sessions'/(c+'-'+d+'.json');p.write_text(json.dumps({'instrument':c,'requested_day':d,'status':'RESPONSE_CAPTURED','response':payload})+'\n')
        h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
        m={'plan_sha256':h(root/'plan.json'),'per_session_sha256':{p.name:h(p)},'complete_capture':True}
        (root/'manifest.json').write_text(json.dumps(m)+'\n')
        bars={c:{d:{'date':d,'tradestatus':'1','isST':'0','low':'9','high':'11','close':'10','volume':'48000'}}}
        return c,d,p,bars,m
    def test_complete_prefix_reuses_observations_but_rechecks_bytes_on_cache_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'source';c,d,p,bars,m=self.fixture(root)
            bank=CompletePrefixTapeBank(root,bars);rows=bank(c,date.fromisoformat(d))
            self.assertEqual(len(rows),48);self.assertEqual(rows[0]['volume_lower_shares'],500)
            self.assertEqual(rows[0]['buy_price'],'10');self.assertEqual(bank(c,date.fromisoformat(d)),rows)
            p.write_bytes(p.read_bytes()+b'\n')
            with self.assertRaises(ValueError):bank(c,date.fromisoformat(d))
    def test_future_missing_or_wrong_capture_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'source';c,d,p,bars,m=self.fixture(root);bank=CompletePrefixTapeBank(root,bars)
            with self.assertRaises(ValueError):bank(c,date(2026,1,5))
            with self.assertRaises(ValueError):bank('SH600009',date.fromisoformat(d))
            (root/'plan.json').write_text('changed')
            with self.assertRaises(ValueError):CompletePrefixTapeBank(root,bars)
    def test_gate_requires_all_three40bps_profiles_not_best_return_or20bps(self):
        base={f'{p}/{cost}':{'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED','2024_return_pct':1.,
            '2025_return_pct':.1,'average_exposure_pct':93.,'monthly_decisions':24,'account_sessions':485,
            'whole_day_volume_violations':0,'noncash_entitlements_supported':True} for p in (100,500,1000) for cost in (20,40)}
        self.assertTrue(confirmation_passes(base))
        for value in (-.01,0.,float('nan'),float('inf'),None,True,'1'):
            bad=copy.deepcopy(base);bad['100/40']['2025_return_pct']=value
            with self.subTest(value=value):self.assertFalse(confirmation_passes(bad))
        for key,value in [('status','INVALID_SOURCE_OR_ACCOUNT'),('average_exposure_pct',89.99),
            ('monthly_decisions',23),('account_sessions',484),('whole_day_volume_violations',1),('noncash_entitlements_supported',False)]:
            bad=copy.deepcopy(base);bad['500/40'][key]=value;self.assertFalse(confirmation_passes(bad))
        for removed in ('100/40','100/20'):
            bad=copy.deepcopy(base);del bad[removed];self.assertFalse(confirmation_passes(bad))
        bad=copy.deepcopy(base);bad['100/20']['2025_return_pct']=100;bad['100/40']['2025_return_pct']=-1
        self.assertFalse(confirmation_passes(bad))
