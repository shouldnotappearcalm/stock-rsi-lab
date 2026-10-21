"""Synthetic source compilation only; no real sources/account replay/network."""
import copy,hashlib,importlib,json,tempfile,unittest
from pathlib import Path
try:m=importlib.import_module('scripts.prepare_price_delay_horizon_events')
except ModuleNotFoundError:m=None

def dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def fixture():
 olddays=['2023-12-29','2024-05-17','2024-05-20','2025-12-31']
 full=sorted(olddays+['2026-04-23','2026-04-24','2026-05-25','2026-05-26','2026-06-03','2026-06-04','2026-06-16','2026-06-17','2026-10-19','2026-10-20'])
 def bars(days):return [{'date':d,'close':'10','preclose':'10'} for d in days]
 def row(code,pub,rec,ex,cash,capital='0',listed=''):
  return {'code':code[:2].lower()+'.'+code[2:],'dividPlanDate':pub,'dividRegistDate':rec,'dividOperateDate':ex,'dividPayDate':ex,
   'dividStockMarketDate':listed,'dividCashPsBeforeTax':cash,'dividStocksPs':'0.000000','dividReserveToStockPs':capital,'dividCashStock':'10派现金' if capital in ('0','') else '10转增派现金'}
 oldrow=row('SH603596','2024-05-14','2024-05-17','2024-05-20','0.34','0.400000','2024-05-20')
 identity={'instrument':'SH603596','source_kind':'VENDOR_DISTRIBUTION','source_distribution':oldrow,'primary_source_sha256':[],
  'effective_stock_taxable_income_per_original_share':'0','capital_tax_exempt_verified':False,'stock_tax_basis_verified':False};eid=dig(identity)
 event={'event_id':eid,'instrument':'SH603596','announced':'2024-05-14','recorded':'2024-05-17','ex_date':'2024-05-20','pay_date':'2024-05-20','listed':'2024-05-20',
 'cash_per_share':'0.34','capital_per_share':'0.400000','capital_tax_exempt_verified':False,'stock_per_share':'0.000000','stock_taxable_income_per_share':'0','stock_tax_basis_verified':False}
 receipt={'event_id':eid,'instrument':'SH603596','ex_date':'2024-05-20','source_kind':'VENDOR_DISTRIBUTION','source_row_sha256':dig(oldrow),'primary_source_sha256':[],
 'blank_capital_resolved_as_zero':False,'requires_zero_record_ownership_if_tax_unverified':True}
 old={'SH603596':{'instrument':'SH603596','bars':bars(olddays),'distributions':[oldrow],'adjustments':[],'quarantine':[]}}
 packets={'SH603596':{**copy.deepcopy(old['SH603596']),'bars':bars(full)}}
 for code,r in [('SH603606',row('SH603606','2026-05-19','2026-05-25','2026-05-26','0.56','0.200000','2026-05-26')),
  ('SZ000937',row('SZ000937','2026-06-11','2026-06-16','2026-06-17','0.1','0.100000','2026-06-17')),
  ('SZ000975',row('SZ000975','2026-04-17','2026-04-23','2026-04-24','0.480402','')),
  ('SZ002831',row('SZ002831','2026-05-29','2026-06-03','2026-06-04','0.803813','0.401906','2026-06-04')),
  ('SH601598',row('SH601598','2024-05-14','2024-05-17','2024-05-20','0.2'))]:
  packets[code]={'instrument':code,'bars':bars(full),'distributions':[r],'adjustments':[],'quarantine':[]}
 d1={'instrument':'SZ000975','day':'2026-04-17','file':'975.pdf','sha256':'1'*64};d2={'instrument':'SZ002831','day':'2026-05-29','file':'2831.pdf','sha256':'2'*64};d3={'instrument':'SH601598','day':'2026-10-13','file':'598.pdf','sha256':'3'*64}
 p={'documents':[d1,d2,d3],'capital_tax':{'SZ002831|2026-06-04':{'verified_exempt':True,'source_file':'2831.pdf','source_sha256':'2'*64,'evidence_kind':'PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE'}},
 'unresolved_tax':{'SH603606|2026-05-26':{'verified_exempt':False},'SZ000937|2026-06-17':{'verified_exempt':False}},'stock_dividend_tax_bases':{},
 'supplementary_distributions':[{'instrument':'SH601598','source_file':'598.pdf','source_sha256':'3'*64,'record':row('SH601598','2026-10-13','2026-10-19','2026-10-20','0.14')}],
 'cash_override_contract':'PRIMARY_NOTICE_CASH_PRECISION_V1','cash_overrides':{'SZ000975|2026-04-24':{'verified':True,'kind':'PRIMARY_NOTICE_CASH_PRECISION','source_file':'975.pdf','source_sha256':'1'*64,
 'source_row_sha256':dig(packets['SZ000975']['distributions'][0]),'expected_vendor_cash_per_share':'0.480402','effective_cash_per_share':'0.4804021'}},
 'component_precision_contract':'PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION_V1','component_precision_overrides':{'SZ002831|2026-06-04':{'verified':True,'kind':'PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION','source_file':'2831.pdf','source_sha256':'2'*64,
 'source_row_sha256':dig(packets['SZ002831']['distributions'][0]),'record_date':'2026-06-03','ex_date':'2026-06-04','cash_payment_date':'2026-06-04','stock_listing_date':'2026-06-04','primary_pages':[1,3,4],
 'components':{'cash_per_share':{'expected_vendor_per_share':'0.803813','primary_per10_original_shares':'8.038127','effective_per_share':'0.8038127'},'capital_per_share':{'expected_vendor_per_share':'0.401906','primary_per10_original_shares':'4.019063','effective_per_share':'0.4019063'}}}}}
 op={'documents':[],'capital_tax':{},'cash_overrides':{},'stock_dividend_tax_bases':{},'supplementary_distributions':[]}
 return old,op,[event],[receipt],packets,p,full

class EventDraftTests(unittest.TestCase):
 def api(self,name):self.assertIsNotNone(m,'event draft missing');self.assertTrue(callable(getattr(m,name,None)),name+' missing');return getattr(m,name)
 def run_core(self,b):
  from stock_rsi.calendar import TradingCalendar
  return self.api('compile_horizon')(*b[:-1],TradingCalendar(b[-1]))
 def test_real_append_then_real_V3_preserves_old_and_replaces_only_mixed(self):
  b=fixture();before=copy.deepcopy(b);events,receipts,stats=self.run_core(b)
  self.assertEqual(len(events),6);self.assertEqual(m.serialize_event(events[0]),b[2][0]);self.assertEqual(receipts[0],b[3][0]);self.assertEqual(b,before)
  bycode={e.instrument:e for e in events};self.assertEqual(str(bycode['SZ002831'].cash_per_share),'0.8038127');self.assertEqual(str(bycode['SZ002831'].capital_per_share),'0.4019063')
  self.assertEqual(str(bycode['SZ000975'].cash_per_share),'0.4804021');self.assertEqual(stats['earlier_rows_of_future_only_names_ignored'],1)
  self.assertEqual(stats['unverified_tax_event_keys'],['SH603606|2026-05-26','SZ000937|2026-06-17'])
  self.assertEqual(stats['source_kind_counts'],{'VENDOR_DISTRIBUTION':3,'PRIMARY_CASH_PRECISION_CORRECTION':1,'PRIMARY_COMPONENT_PRECISION_CORRECTION':1,'PRIMARY_NOTICE_SUPPLEMENT':1})
 def test_wrong_old_receipt_or_raw_prefix_rejected(self):
  b=fixture();b[3][0]['requires_zero_record_ownership_if_tax_unverified']=False;self.assertRaises(ValueError,self.run_core,b)
  b=fixture();b[4]['SH603596']['bars'][0]['close']='11';self.assertRaises(ValueError,self.run_core,b)
 def test_unknown_tax_cannot_be_upgraded(self):
  b=fixture();b[5]['unresolved_tax']['SZ000937|2026-06-17']['verified_exempt']=True;self.assertRaises(ValueError,self.run_core,b)
 def test_component_correction_cannot_target_old_event_or_second_key(self):
  b=fixture();proof=b[5]['component_precision_overrides'];proof['SH603596|2024-05-20']=copy.deepcopy(next(iter(proof.values())));self.assertRaises(ValueError,self.run_core,b)
 def test_wrong_mixed_raw_row_or_primary_reference_rejected(self):
  b=fixture();b[5]['component_precision_overrides']['SZ002831|2026-06-04']['source_row_sha256']='0'*64;self.assertRaises(ValueError,self.run_core,b)
  b=fixture();b[5]['component_precision_overrides']['SZ002831|2026-06-04']['components']['cash_per_share']['effective_per_share']='0.7991573';self.assertRaises(ValueError,self.run_core,b)
 def test_duplicate_supplement_rejected_without_new_receipt(self):
  b=fixture();b[5]['supplementary_distributions'].append(copy.deepcopy(b[5]['supplementary_distributions'][0]));self.assertRaises(ValueError,self.run_core,b)
 def test_coverage_does_not_pull_future_only_history_into_account(self):
  fn=self.api('validate_coverage');b=fixture();events,_,_=self.run_core(b);fn(b[0],b[4],events)
  b[4]['SH601598']['bars'][4]['preclose']='9';self.assertRaises(ValueError,fn,b[0],b[4],events)
 def test_changed_file_digest_rejected_and_paths_bounded(self):
  fn=self.api('authenticate_map')
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a.json';p.write_text('{}');fn(Path(t),{'a.json':hashlib.sha256(p.read_bytes()).hexdigest()});p.write_text('{"changed":1}');self.assertRaises(ValueError,fn,Path(t),{'a.json':hashlib.sha256(b'{}').hexdigest()});self.assertRaises(ValueError,fn,Path(t),{'../escape':'0'*64})
 def test_draft_plan_and_missing_exact_method_key_fail_before_compile(self):
  fn=self.api('validate_plan');p=self.api('plan_template')();self.assertRaises(ValueError,fn,p)
  p['status']='FROZEN_PRICE_DELAY_HORIZON_APPEND_ONLY_SOURCE_EVENTS_NO_ROI'
  for field in ['method_code_sha256','public_evidence_sha256','local_source_sha256']:
   p[field]={k:'0'*64 for k in p[field]}
  p['financial_artifact_sha256']={'financial/'+str(i):'0'*64 for i in range(48)};p['primary_document_sha256']={'pdf/'+str(i):'0'*64 for i in range(32)}
  fn(p);p['method_code_sha256'].pop(next(iter(p['method_code_sha256'])));self.assertRaises(ValueError,fn,p)
 def test_existing_or_wrong_output_never_overwritten(self):
  fn=self.api('validate_destination')
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);out=root/'price-delay-account-horizon-events-20261021';fn(root,out);out.mkdir();p=out/'keep';p.write_text('original');self.assertRaises(ValueError,fn,root,out);self.assertEqual(p.read_text(),'original');self.assertRaises(ValueError,fn,root,root/'wrong')
 def test_48_financial_bytes_checked_not_only_unchanged_summary_map(self):
  fn=self.api('authenticate_financial_files')
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);bindings={}
   for i in range(48):p=root/(str(i)+'.csv');p.write_text('frozen synthetic '+str(i));bindings[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
   fn(root,bindings,copy.deepcopy(bindings));(root/'23.csv').write_text('changed actual bytes; summary mapping remains unchanged')
   self.assertRaises(ValueError,fn,root,bindings,copy.deepcopy(bindings))
 def test_old_audit_anchor_rejects_coherently_rebound_summary_or_false_identity(self):
  fn=self.api('verify_old_audit_anchor')
  audit={'status':'INDEPENDENT_378_EVENT_ECONOMICS_IDENTITIES_AND_SOURCE_RECEIPTS_RECONSTRUCTED','summary_sha256':'1'*64,
   'reviewed_manifest_sha256':'2'*64,'raw_manifest_sha256':'3'*64,'events_reconstructed':378,'all378_economics_dates_event_IDs_and_receipts_identical':True}
  fn(audit,'1'*64,'2'*64,'3'*64)
  self.assertRaises(ValueError,fn,audit,'4'*64,'2'*64,'3'*64)
  bad=copy.deepcopy(audit);bad['all378_economics_dates_event_IDs_and_receipts_identical']=False;self.assertRaises(ValueError,fn,bad,'1'*64,'2'*64,'3'*64)

 def test_original_producer_raw_review_and_target_links_not_rebound(self):
  fn=self.api('verify_original_producer_links');summary={'raw_manifest_sha256':'1'*64,'reviewed_manifest_sha256':'2'*64,'target_sha256':'3'*64}
  fn(summary,'1'*64,'2'*64,'3'*64);self.assertRaises(ValueError,fn,summary,'1'*64,'2'*64,'4'*64)

 def test_projection_independent_audit_anchors_required_before_events(self):
  fn=self.api('verify_projection_audit_anchor')
  a={'reviewed_manifest_sha256':'1'*64,'summary_sha256':'2'*64,'all17_PDFs_byte_exact':True,'all_projected_proof_objects_independently_reconstructed':True,'critical_or_important_findings':[]}
  fn(a,'1'*64,'2'*64);self.assertRaises(ValueError,fn,a,'3'*64,'2'*64)
  a['all_projected_proof_objects_independently_reconstructed']=False;self.assertRaises(ValueError,fn,a,'1'*64,'2'*64)

if __name__=='__main__':unittest.main(verbosity=2)
