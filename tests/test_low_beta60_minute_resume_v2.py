import hashlib,json,tempfile,unittest
from pathlib import Path
from scripts.capture_low_beta60_minutes_pre2026 import capture_prefix
try:
    from scripts.capture_low_beta60_minutes_pre2026_v2 import capture_prefix_v2
except ImportError:
    capture_prefix_v2=None


class LowBeta60StrictResumeTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(capture_prefix_v2)
    def seed(self,base,fresh=None,fetch=None):
        out=base/'capture';out.mkdir();request={'fixture':'frozen'}
        (out/'request.json').write_text(json.dumps(request,indent=2)+'\n')
        h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        fresh=fresh or [['SH600001','2024-06-03']]
        plan={'host':'fixture','max_fresh_query_reservations':len(fresh),'max_attempts_per_request':1,
            'stop_after_consecutive_source_failures':3,'inter_query_delay_seconds':0,'request_sha256':h(out/'request.json')}
        if fetch is None:fetch=lambda c,d:{'code':c,'trading_date':d,'points':[]}
        try:capture_prefix(base,out,{},fresh,plan,fetch)
        except KeyboardInterrupt:pass
        return out,fresh,plan,h(out/'manifest.json')
    def test_verified_complete_capture_is_read_only_and_never_calls_source(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);out,fresh,plan,expected=self.seed(base);calls=[]
            hashes=lambda:{str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}
            before=hashes();result=capture_prefix_v2(base,out,{},fresh,plan,lambda c,d:calls.append([c,d]),expected_manifest_sha256=expected)
            self.assertTrue(result['complete_capture']);self.assertEqual(calls,[]);self.assertEqual(hashes(),before)
    def test_format_only_change_to_source_config_request_or_snapshot_is_rejected_before_fetch(self):
        for kind in ('session','plan','capture_request','request','manifest','snapshot','response'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                base=Path(directory);out,fresh,plan,expected=self.seed(base);calls=[]
                if kind=='session':f=next((out/'sessions').glob('*.json'))
                elif kind=='snapshot':f=next(out.glob('capture-snapshot-*.json'))
                elif kind=='response':f=next((out/'queries').glob('*/response-1.json'))
                else:f=out/(kind+'.json')
                f.write_bytes(f.read_bytes()+b'\n')
                with self.assertRaises(ValueError):capture_prefix_v2(base,out,{},fresh,plan,lambda c,d:calls.append(1),expected_manifest_sha256=expected)
                self.assertEqual(calls,[])
    def test_reserved_unanswered_attempt_stays_consumed_and_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);fresh=[['SH600001','2024-06-03'],['SH600002','2024-06-03']]
            def fetch(c,d):
                if c=='SH600002':raise KeyboardInterrupt('fixture interrupted after reservation')
                return {'code':c,'trading_date':d,'points':[]}
            out,fresh,plan,expected=self.seed(base,fresh,fetch);calls=[]
            with self.assertRaises(ValueError):capture_prefix_v2(base,out,{},fresh,plan,lambda c,d:calls.append(1),expected_manifest_sha256=expected)
            self.assertEqual(calls,[]);self.assertEqual(len(list(out.glob('queries/*/reserved-1.json'))),2)
            self.assertEqual(len(list(out.glob('queries/*/response-1.json'))),1)
    def test_more_than493_or_existing_untrusted_state_never_calls_source(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);fresh=[['SH'+str(600000+i),'2024-06-03'] for i in range(494)];calls=[]
            plan={'host':'fixture','max_fresh_query_reservations':494,'max_attempts_per_request':1,
                'stop_after_consecutive_source_failures':3,'inter_query_delay_seconds':0}
            with self.assertRaises(ValueError):capture_prefix_v2(base,base/'new',{},fresh,plan,lambda c,d:calls.append(1))
            out,fresh,plan,expected=self.seed(base)
            with self.assertRaises(ValueError):capture_prefix_v2(base,out,{},fresh,plan,lambda c,d:calls.append(1))
            self.assertEqual(calls,[])
