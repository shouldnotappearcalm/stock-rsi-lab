import hashlib,json,tempfile,unittest
from pathlib import Path
from stock_rsi.calendar import TradingCalendar
from scripts.run_low_beta60_intraday_development import CompletePrefixTapeBank
from scripts.tdx_history_checks import minute_labels
try:
    from scripts.run_low_beta60_intraday_development_v2 import SourceIOGuard,run_profiles
except ImportError:
    SourceIOGuard=run_profiles=None


class LowBeta60SourceFailureRetentionTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(SourceIOGuard);self.assertIsNotNone(run_profiles)
    def fixture(self,base):
        capture=base/'source';capture.mkdir();(capture/'sessions').mkdir();(capture/'plan.json').write_text('{}\n')
        code='SH600008';day='2024-01-02';path=capture/'sessions'/(code+'-'+day+'.json');path.write_text('{}\n')
        h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        (capture/'manifest.json').write_text(json.dumps({'complete_capture':True,'plan_sha256':h(capture/'plan.json'),
            'per_session_sha256':{path.name:h(path)}})+'\n')
        days=['2023-12-29',day]
        bars={code:{d:{'code':'sh.600008','date':d,'tradestatus':'1','isST':'0','open':'10','preclose':'10',
            'close':'10','high':'10','low':'10','volume':'1000000'} for d in days}}
        bank=CompletePrefixTapeBank(capture,bars);targets={day:{'as_of':days[0],'weights':{code:'.95'}}}
        return path,bars,bank,targets,TradingCalendar(days)
    def test_missing_source_file_becomes_typed_source_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path,bars,bank,targets,calendar=self.fixture(Path(directory));guard=SourceIOGuard(bank);path.unlink()
            with self.assertRaisesRegex(ValueError,'source IO'):guard('SH600008',calendar.days[-1])
    def test_real_account_source_disappearance_preserves_every_profile_and_parent_state(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);path,bars,bank,targets,calendar=self.fixture(base)
            code='SH600008';days=['2023-12-29','2024-01-02','2024-01-31','2024-02-01']
            bars[code].update({d:{**bars[code]['2024-01-02'],'date':d,'volume':'1200000000'} for d in days})
            for d in ('2024-01-02','2024-02-01'):
                payload={'exchange':'sh','market_id':1,'code':'600008','trading_date':d,
                    'points':[{'index':i,'time_label':s,'time':d+'T'+s+':00+08:00',
                        'price_milli':10000,'price':10,'volume':50000} for i,s in enumerate(minute_labels())]}
                (path.parent/(code+'-'+d+'.json')).write_text(json.dumps({'instrument':code,'requested_day':d,
                    'status':'RESPONSE_CAPTURED','response':payload})+'\n')
            capture=path.parent.parent;m=json.loads((capture/'manifest.json').read_text())
            m['per_session_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in path.parent.glob('*.json')}
            (capture/'manifest.json').write_text(json.dumps(m)+'\n');bank=CompletePrefixTapeBank(capture,bars)
            targets['2024-02-01']={'as_of':'2024-01-31','weights':{code:'.50'}};calendar=TradingCalendar(days)
            missing=path.parent/(code+'-2024-02-01.json')
            class DisappearingSource:
                index=bank.index;accessed=bank.accessed
                def __call__(self,code,day):
                    if day.isoformat()=='2024-02-01' and missing.exists():missing.unlink()
                    return bank(code,day)
            out=base/'out';results=run_profiles(out,calendar,bars,(),targets,DisappearingSource())
            self.assertEqual(set(results),{f'{p}/{c}' for p in (100,500,1000) for c in (20,40)})
            self.assertEqual(json.loads((out/'case_results.json').read_text()),results)
            for key,r in results.items():
                self.assertEqual(r['status'],'INVALID_SOURCE_OR_ACCOUNT');self.assertIn('source IO',r['error'])
                self.assertIn('failed_account_state.json',r['failure_artifact_sha256'])
                state=json.loads((out/key/'failed_account_state.json').read_text())
                self.assertEqual(len(state['parent_instructions']),2);self.assertGreater(len(state['fills']),0)
                self.assertGreater(state['owned_shares'][code],0)
                self.assertGreater(float(state['cash']),0);self.assertLess(float(state['cash']),1000000)
                self.assertEqual(state['last_account_clock'],['2024-02-01',0])
                for name,h in r['failure_artifact_sha256'].items():
                    self.assertEqual(hashlib.sha256((out/key/name).read_bytes()).hexdigest(),h)
