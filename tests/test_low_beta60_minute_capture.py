import hashlib,json,tempfile,unittest
from pathlib import Path
from scripts.fundamental_query_journal import digest
try:
    from scripts.capture_low_beta60_minutes_pre2026 import capture_prefix
except ImportError:
    capture_prefix=None


class LowBeta60MinuteCaptureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(capture_prefix)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.out=self.base/'new';self.calls=[]
    def plan(self,n):return {'host':'fixture','max_fresh_query_reservations':n,
        'max_attempts_per_request':1,'stop_after_consecutive_source_failures':3,'inter_query_delay_seconds':0}
    def fetch(self,c,d):self.calls.append([c,d]);return {'code':c,'trading_date':d,'points':[]}
    def cached(self):
        p=self.base/'old/sessions/SH600001-2024-06-03.json';p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'instrument':'SH600001','requested_day':'2024-06-03',
            'status':'RESPONSE_CAPTURED','response':{'original':'fixture'}},indent=4)+'\n')
        return p,{p.name:{'root':'old','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}}
    def test_copy_bytes_and_restart_do_not_repeat_success_or_failed_fetch(self):
        source,reused=self.cached();fresh=[['SH600002','2024-06-03'],['SH600003','2024-06-03']]
        def fetch(c,d):
            self.calls.append([c,d])
            if c=='SH600003':raise RuntimeError('fixture failure')
            return {'code':c,'trading_date':d,'points':[]}
        first=capture_prefix(self.base,self.out,reused,fresh,self.plan(2),fetch)
        again=capture_prefix(self.base,self.out,reused,fresh,self.plan(2),fetch)
        self.assertEqual(first,again);self.assertEqual(len(self.calls),2)
        self.assertEqual((self.out/'sessions'/source.name).read_bytes(),source.read_bytes())
        self.assertEqual(first['fresh_query_reservations'],2)
        self.assertEqual(first['response_status_counts'],{'RESPONSE_CAPTURED':2,'REQUEST_FAILED':1})
        self.assertTrue(first['complete_capture']);self.assertFalse(first['admitted_for_reconstructed_execution'])
    def test_corrupted_cache_is_rejected_before_any_fetch_or_output_creation(self):
        source,reused=self.cached();source.write_text('changed')
        with self.assertRaises(ValueError):capture_prefix(self.base,self.out,reused,[['SH600002','2024-06-03']],self.plan(1),self.fetch)
        self.assertEqual(self.calls,[]);self.assertFalse(self.out.exists())
    def test_future_duplicate_overlap_and_wrong_budget_rejected_before_fetch(self):
        _,reused=self.cached()
        cases=[([['SH600002','2024-06-03'],['SH600003','2026-01-05']],self.plan(2)),
            ([['SH600002','2024-06-03']]*2,self.plan(2)),([['SH600001','2024-06-03']],self.plan(1)),
            ([['SH600002','2024-06-03']],self.plan(2))]
        for fresh,plan in cases:
            with self.subTest(fresh=fresh),self.assertRaises(ValueError):capture_prefix(self.base,self.out,reused,fresh,plan,self.fetch)
        self.assertEqual(self.calls,[]);self.assertFalse(self.out.exists())
    def test_interrupted_reservation_consumed_and_partial_manifest_preserved(self):
        fresh=[['SH600002','2024-06-03']];self.out.mkdir()
        identity={'method':'minutes.history','instrument':'SH600002','requested_day':'2024-06-03','host':'fixture','include_raw':True}
        folder=self.out/'queries'/digest(identity);folder.mkdir(parents=True)
        (folder/'request.json').write_text(json.dumps(identity))
        (folder/'reserved-1.json').write_text(json.dumps({'identity_sha256':digest(identity),'attempt':1}))
        with self.assertRaises(ValueError):capture_prefix(self.base,self.out,{},fresh,self.plan(1),self.fetch)
        self.assertEqual(self.calls,[])
        m=json.loads((self.out/'manifest.json').read_text());self.assertEqual(m['fresh_query_reservations'],1)
        self.assertFalse(m['complete_capture']);self.assertEqual(m['captured'],0);self.assertIsNotNone(m['abnormal_exit'])
    def test_stop_three_failures_cannot_be_bypassed_by_restart(self):
        fresh=[['SH60000'+str(i),'2024-06-03'] for i in range(1,5)]
        def fail(c,d):self.calls.append([c,d]);raise RuntimeError('fixture unavailable')
        first=capture_prefix(self.base,self.out,{},fresh,self.plan(4),fail)
        second=capture_prefix(self.base,self.out,{},fresh,self.plan(4),fail)
        self.assertEqual(first,second);self.assertEqual(len(self.calls),3)
        self.assertTrue(first['stopped_after_consecutive_source_failures']);self.assertFalse(first['complete_capture'])
        self.assertEqual(first['fresh_query_reservations'],3)
