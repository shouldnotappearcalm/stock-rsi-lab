import copy,hashlib,json,tempfile,unittest
from pathlib import Path
try:
 from scripts.capture_price_delay_minutes_pre2026 import validate_profile,require_new_output,main
except ImportError:validate_profile=require_new_output=main=None


class PriceDelayMinuteCaptureTests(unittest.TestCase):
 def setUp(self):self.assertIsNotNone(validate_profile)
 def profile(self):return {'status':'FROZEN_PRICE_DELAY_PRE2026_MINUTE_SOURCE_CAPTURE','candidate':'price_delay_d1',
  'window':['2024-01-02','2025-12-31'],'package_version':'3.2.3','host':'116.205.183.150:7709',
  'timeout_seconds':3,'pool_size':1,'server_count':1,'connections_per_server':1,'heartbeat_interval':None,'probe_hosts':False,
  'max_fresh_query_reservations':918,'max_attempts_per_request':1,'stop_after_consecutive_source_failures':3,
  'inter_query_delay_seconds':.05,'required_source_pairs':2502,'existing_source_pairs_to_reuse':1584}
 def test_exact_profile_rejects_expanded_or_future_source_access(self):
  original=self.profile();validate_profile(original)
  for key,value in [('candidate','low_delay_control'),('window',['2024-01-02','2026-01-05']),
   ('host','other:7709'),('package_version','3.2.4'),('max_fresh_query_reservations',919),
   ('max_attempts_per_request',2),('stop_after_consecutive_source_failures',4),('timeout_seconds',4),
   ('pool_size',2),('server_count',2),('connections_per_server',2),('probe_hosts',True),
   ('heartbeat_interval',30),('inter_query_delay_seconds',0),('existing_source_pairs_to_reuse',1583),('pool_size',True)]:
   p=copy.deepcopy(original);p[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):validate_profile(p)
 def test_existing_capture_directory_cannot_be_restarted_or_replaced(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'capture';require_new_output(out);self.assertFalse(out.exists())
   out.mkdir();f=out/'reserved-attempt.json';f.write_bytes(b'untouched')
   with self.assertRaises(ValueError):require_new_output(out)
   self.assertEqual(f.read_bytes(),b'untouched')
 def test_wrong_external_plan_checksum_fails_before_output_or_source_access(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);plan=root/'plan.json';plan.write_text(json.dumps(self.profile()));out=root/'capture'
   with self.assertRaisesRegex(ValueError,'capture plan changed'):
    main(['--source-root',str(root/'absent'),'--request',str(root/'absent.json'),'--plan',str(plan),
     '--expected-plan-sha256','0'*64,'--output-dir',str(out),'--preflight-only'])
   self.assertFalse(out.exists());self.assertTrue(plan.exists())

if __name__=='__main__':unittest.main()
