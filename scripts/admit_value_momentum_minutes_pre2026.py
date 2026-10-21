"""Composite scope checks for a separately frozen local-only source admission."""


def verify_capture_scope(scope,manifest,cleanup,*,capture_plan_sha256,request_sha256,manifest_sha256,cleanup_sha256):
 expected={'status':'COMPOSITE_PRE2026_MINUTE_CAPTURE_RECORDED','candidate':'szse_value_momentum_equal',
  'capture_plan_sha256':capture_plan_sha256,'request_sha256':request_sha256,
  'legacy_helper_manifest_sha256':manifest_sha256,'cleanup_sha256':cleanup_sha256,
  'legacy_status_marker_preserved':True,'expected_active_pairs':1744,'fixed_reused_pairs':1051,
  'maximum_fresh_logical_reservations':693,'new_2026_queries':False,
  'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
 if (any(scope.get(k)!=v or type(scope.get(k)) is not type(v) for k,v in expected.items())
     or manifest.get('status')!='LOW_BETA60_PRE2026_MINUTE_CAPTURE_RECORDED'
     or type(manifest.get('complete_capture')) is not bool
     or scope.get('complete_capture') is not manifest['complete_capture']):
  raise ValueError('actual legacy capture and separate composite scope must bind exactly')
 rows=cleanup['closed_clients'];created=cleanup['created_clients']
 if (type(created) is not int or not 0<=created<=693 or not isinstance(rows,list) or len(rows)!=created
     or any(type(r.get('entered')) is not bool or r.get('close_called') is not True
      or 'error' not in r or r['error'] is not None and not isinstance(r['error'],str) for r in rows)):
  raise ValueError('complete source-client cleanup record required')
 # Failed initialization/cleanup stays inspectable; it never grants admission.
 return created==1 and rows[0]['entered'] is True and rows[0]['error'] is None
