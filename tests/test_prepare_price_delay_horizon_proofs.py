"""Synthetic request scope failures before any actual source processing."""
import copy
import unittest
from scripts import prepare_price_delay_horizon_proofs as m


def plan():
 return {**copy.deepcopy(m.PROFILE),'method_code_sha256':{x:'0'*64 for x in m.METHODS},
  'public_evidence_sha256':{x:'0'*64 for x in m.PUBLIC},'local_source_sha256':{x:'0'*64 for x in m.LOCAL},
  'immutable_trees_sha256':{x:{} for x in (m.raw.SOURCE,m.raw.PRIMARY,'price-delay-horizon-remaining-primary-20261021',m.OLDPDF,m.OLDEVENTS)},
  'primary_evidence':{name:{'route':route,'source_manifest_file':cap+'/'+manifest,'source_document_file':name,
   'pdf_file':cap+'/'+name,'content_review_refs':[{'root':'repo','file':'experiments/qlib/'+review}],
   **({'capture_root':cap} if route=='HTTP' else {})} for name,(cap,manifest,review,route) in m.DOCUMENT_ROUTES.items()}}


class FrozenProofScope(unittest.TestCase):
 def test_complete_source_only_scope(self):m.validate_profile(plan())
 def test_missing_original_tree_rejected(self):
  p=plan();p['immutable_trees_sha256'].pop(m.raw.SOURCE)
  with self.assertRaises(ValueError):m.validate_profile(p)
 def test_source_route_or_content_review_cannot_be_changed(self):
  for field,value in [('route','REVIEWED_BYTE_REUSE'),('source_manifest_file','different.json'),('content_review_refs',[])]:
   p=plan();p['primary_evidence']['SH603233.pdf'][field]=value
   with self.assertRaises(ValueError):m.validate_profile(p)
 def test_no_query_or_account_scope_upgrade(self):
  for k in ('maximum_new_source_queries','account_to_run','events_to_compile','portfolio_returns_to_compute'):
   p=plan();p[k]=1
   with self.assertRaises(ValueError):m.validate_profile(p)
 def test_method_subset_rejected(self):
  p=plan();p['method_code_sha256'].pop(m.METHODS[-1])
  with self.assertRaises(ValueError):m.validate_profile(p)

 def test_original_independent_audit_is_canonical_anchor(self):
  a={'status':'INDEPENDENT_378_EVENT_ECONOMICS_IDENTITIES_AND_SOURCE_RECEIPTS_RECONSTRUCTED',
   'summary_sha256':'s','reviewed_manifest_sha256':'p','raw_manifest_sha256':'r',
   'all378_economics_dates_event_IDs_and_receipts_identical':True,
   'all151_source_packets_authenticated':True,'all15_primary_PDF_bytes_and_two_content_reviews_authenticated':True,
   'events_reconstructed':378,'critical_or_important_findings':0,'imports_project_code':False}
  m.validate_old_audit(a,'s','p','r',378,378)
  # A new request/tree/summary may be mutually consistent but must not replace
  # the version that the original independent audit actually reconstructed.
  for args in [('coherently-new-summary','p','r',378,378),('s','new-proof','r',378,378),
               ('s','p','new-raw',378,378),('s','p','r',377,378)]:
   with self.assertRaises(ValueError):m.validate_old_audit(a,*args)
  for key in ('all378_economics_dates_event_IDs_and_receipts_identical','all151_source_packets_authenticated'):
   b=copy.deepcopy(a);b[key]=False
   with self.assertRaises(ValueError):m.validate_old_audit(b,'s','p','r',378,378)


if __name__=='__main__':unittest.main()
