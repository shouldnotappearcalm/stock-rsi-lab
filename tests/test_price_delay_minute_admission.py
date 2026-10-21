import copy,tempfile,unittest
from pathlib import Path
from scripts.fundamental_query_journal import file_sha
from scripts.admit_price_delay_minutes_pre2026 import verify_journal_bytes
from scripts import admit_price_delay_minutes_pre2026 as admission
try:
 from scripts.admit_price_delay_minutes_pre2026 import verify_capture_scope
except ImportError:verify_capture_scope=None


class PriceDelayMinuteAdmissionScopeTests(unittest.TestCase):
 def test_plan_rejects_future_window_network_budget_missing_anchors_and_wrong_output(self):
  plan={'status':'FROZEN_PRICE_DELAY_PRE2026_MINUTE_SOURCE_ADMISSION','candidate':'price_delay_d1',
   'required_active_sessions':2502,'fixed_reused_pairs':1584,'exact_fresh_reservations':918,
   'nonexecuting_source_intervals':2,'window':['2024-01-02','2025-12-31'],
   'network_calls_permitted':0,'portfolio_returns_computed':False,'new_2026_market_values_queried':False,
   'candidate_promoted':False,'objective_achieved':False,'output_relative':'price-delay-minute-admission-20261021',
   'method_code_sha256':dict.fromkeys(admission.METHOD_FILES,'a'*64),
   'public_evidence_sha256':dict.fromkeys(admission.PUBLIC_FILES,'b'*64),
   'local_source_sha256':dict.fromkeys(admission.LOCAL_FILES,'c'*64)}
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);out=base/plan['output_relative'];admission.validate_admission_plan(plan,base,out)
   for key,value in [('window',['2024-01-02','2026-01-01']),('network_calls_permitted',1),
    ('fixed_reused_pairs',1583),('exact_fresh_reservations',919),('portfolio_returns_computed',True),
    ('method_code_sha256',{}),('public_evidence_sha256',{}),('local_source_sha256',{}),
    ('output_relative','../escaped')]:
    changed=copy.deepcopy(plan);changed[key]=value
    with self.subTest(key=key),self.assertRaises(ValueError):admission.validate_admission_plan(changed,base,out)
   with self.assertRaises(ValueError):admission.validate_admission_plan(plan,base,base/'other')
 def test_audited_journal_bytes_cannot_be_reformatted_or_extended(self):
  with tempfile.TemporaryDirectory() as d:
   capture=Path(d);folder=capture/'queries'/'fixed-request';folder.mkdir(parents=True)
   request=folder/'request.json';request.write_text('{"instrument":"SZ000001"}')
   audit={'query_artifact_sha256':{'queries/fixed-request/request.json':file_sha(request)}}
   verify_journal_bytes(capture,audit)
   request.write_text('{ "instrument": "SZ000001" }')
   with self.assertRaises(ValueError):verify_journal_bytes(capture,audit)
   request.write_text('{"instrument":"SZ000001"}');extra=folder/'unexpected.json';extra.write_text('{}')
   with self.assertRaises(ValueError):verify_journal_bytes(capture,audit)
   extra.unlink();verify_journal_bytes(capture,audit)
 def setUp(self):self.assertIsNotNone(verify_capture_scope)
 def fixture(self):
  scope={'status':'PRICE_DELAY_PRE2026_MINUTE_CAPTURE_RECORDED','candidate':'price_delay_d1',
   'capture_plan_sha256':'a'*64,'request_sha256':'b'*64,'legacy_helper_manifest_sha256':'c'*64,'cleanup_sha256':'d'*64,
   'legacy_status_marker_preserved':True,'expected_active_pairs':2502,'fixed_reused_pairs':1584,
   'maximum_fresh_logical_reservations':918,'complete_capture':True,'new_2026_queries':False,
   'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
  manifest={'status':'LOW_BETA60_PRE2026_MINUTE_CAPTURE_RECORDED','complete_capture':True}
  cleanup={'created_clients':1,'closed_clients':[{'entered':True,'close_called':True,'error':None}]}
  hashes={'capture_plan_sha256':'a'*64,'request_sha256':'b'*64,'manifest_sha256':'c'*64,'cleanup_sha256':'d'*64}
  return scope,manifest,cleanup,hashes
 def test_legacy_marker_cannot_stand_in_for_matching_price_delay_identity(self):
  scope,manifest,cleanup,hashes=self.fixture();self.assertTrue(verify_capture_scope(scope,manifest,cleanup,**hashes))
  for key,value in [('candidate','low_beta60'),('legacy_helper_manifest_sha256','e'*64),('request_sha256','e'*64),
   ('capture_plan_sha256','e'*64),('cleanup_sha256','e'*64),('expected_active_pairs',2501),
   ('maximum_fresh_logical_reservations',919),('new_2026_queries',True),('complete_capture',False)]:
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
