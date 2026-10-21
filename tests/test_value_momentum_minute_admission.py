import copy,unittest
try:
 from scripts.admit_value_momentum_minutes_pre2026 import verify_capture_scope
except ImportError:verify_capture_scope=None


class CompositeMinuteAdmissionScopeTests(unittest.TestCase):
 def setUp(self):self.assertIsNotNone(verify_capture_scope)
 def fixture(self):
  scope={'status':'COMPOSITE_PRE2026_MINUTE_CAPTURE_RECORDED','candidate':'szse_value_momentum_equal',
   'capture_plan_sha256':'a'*64,'request_sha256':'b'*64,'legacy_helper_manifest_sha256':'c'*64,'cleanup_sha256':'d'*64,
   'legacy_status_marker_preserved':True,'expected_active_pairs':1744,'fixed_reused_pairs':1051,
   'maximum_fresh_logical_reservations':693,'complete_capture':True,'new_2026_queries':False,
   'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
  manifest={'status':'LOW_BETA60_PRE2026_MINUTE_CAPTURE_RECORDED','complete_capture':True}
  cleanup={'created_clients':1,'closed_clients':[{'entered':True,'close_called':True,'error':None}]}
  hashes={'capture_plan_sha256':'a'*64,'request_sha256':'b'*64,'manifest_sha256':'c'*64,'cleanup_sha256':'d'*64}
  return scope,manifest,cleanup,hashes
 def test_legacy_marker_cannot_stand_in_for_matching_composite_identity(self):
  scope,manifest,cleanup,hashes=self.fixture();self.assertTrue(verify_capture_scope(scope,manifest,cleanup,**hashes))
  for key,value in [('candidate','low_beta60'),('legacy_helper_manifest_sha256','e'*64),('request_sha256','e'*64),
   ('capture_plan_sha256','e'*64),('cleanup_sha256','e'*64),('expected_active_pairs',1743),
   ('maximum_fresh_logical_reservations',694),('new_2026_queries',True),('complete_capture',False)]:
   changed=copy.deepcopy(scope);changed[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):verify_capture_scope(changed,manifest,cleanup,**hashes)
 def test_cleanup_failures_remain_visible_and_cannot_admit_complete_source(self):
  scope,manifest,cleanup,hashes=self.fixture();original=copy.deepcopy(cleanup)
  cleanup['closed_clients'][0]['error']='fixture close failure'
  self.assertFalse(verify_capture_scope(scope,manifest,cleanup,**hashes));self.assertEqual(cleanup['closed_clients'][0]['error'],'fixture close failure')
  cleanup=copy.deepcopy(original);cleanup['closed_clients'][0]['entered']=False
  self.assertFalse(verify_capture_scope(scope,manifest,cleanup,**hashes))
  cleanup=copy.deepcopy(original);cleanup['created_clients']=2
  with self.assertRaises(ValueError):verify_capture_scope(scope,manifest,cleanup,**hashes)

if __name__=='__main__':unittest.main()
