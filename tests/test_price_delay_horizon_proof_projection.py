"""Synthetic behavior tests; no real source inputs or project imports."""
import base64,copy,hashlib,importlib,json,tempfile,unittest
from pathlib import Path
try:m=importlib.import_module('scripts.price_delay_horizon_proof_projection')
except ModuleNotFoundError:m=None

def dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def h(v):return hashlib.sha256(v).hexdigest()

def fixture():
 docs={};pdf={}
 def doc(code,pub,ex,cash,cap='0',rec=None,kind=None,name=None):
  name=name or code+'-'+pub.replace('-','')+'.pdf';content=b'%PDF synthetic '+name.encode();pdf[name]=content
  d={'instrument':code,'file':name,'sha256':h(content),'day':pub,'publication_day':pub,'ex_date':ex,
   'record_date':rec or ex,'cash_payment_date':ex,'stock_listing_date':ex if cap!='0' else None,
   'cash_per_original_share_CNY':cash,'capital_per_original_share':cap,'stock_per_original_share':'0','primary_pages':[1,2,3],
   'direct_premium_source_and_no_tax_statement':kind=='DIRECT','capital_tax_evidence_level':kind or 'NOT_APPLICABLE',
   'price_reference_cash_per_share_CNY':'0.01','all_pages_independently_text_and_visual_reviewed':True}
  docs[name]=d;return d
 def row(d,cash=None,cap=None):return {'code':d['instrument'][:2].lower()+'.'+d['instrument'][2:],'dividPlanDate':d['day'],
  'dividRegistDate':d['record_date'],'dividOperateDate':d['ex_date'],'dividPayDate':d['cash_payment_date'],
  'dividStockMarketDate':d['stock_listing_date'] or '', 'dividCashPsBeforeTax':cash or d['cash_per_original_share_CNY'],
  'dividStocksPs':'0.000000','dividReserveToStockPs':cap or d['capital_per_original_share'],'dividCashStock':'synthetic literal'}
 cached={'cache-a':{'documents':[],'capital_tax':{},'unresolved_tax':{},'cash_overrides':{},'supplementary_distributions':[]}}
 c=cached['cache-a'];packets={};notices={}
 cash=[('SH601598','2026-10-13','2026-10-19','2026-10-20','0.14'),('SH601918','2026-01-30','2026-02-05','2026-02-06','0.05'),
 ('SH601966','2026-06-16','2026-06-23','2026-06-24','0.042'),('SZ002608','2026-10-13','2026-10-16','2026-10-19','0.05'),
 ('SZ002756','2026-10-14','2026-10-19','2026-10-20','0.3'),('SZ002812','2026-10-14','2026-10-19','2026-10-20','0.41')]
 for code,pub,rec,ex,amount in cash:
  d=doc(code,pub,ex,amount,rec=rec);packets[code]={'instrument':code,'distributions':[]};c['documents'].append(d)
  c['supplementary_distributions'].append({'instrument':code,'record':row(d),'source_file':d['file'],'source_sha256':d['sha256'],'record_origin':'unchanged old reviewed source'})
 for code,pub,rec,ex,cash,cap,kind in [('SH601128','2026-06-03','2026-06-08','2026-06-09','0.12','0.100000','DIRECT'),
  ('SH603737','2026-05-26','2026-05-29','2026-06-01','0.068','0.200000','DIRECT'),
  ('SZ002595','2026-04-30','2026-05-08','2026-05-11','1','0.450000','CONDITIONAL')]:
  d=doc(code,pub,ex,cash,cap,rec,kind);c['documents'].append(d);packets[code]={'instrument':code,'distributions':[row(d)]}
  p={'verified_exempt':True,'source_file':d['file'],'source_sha256':d['sha256'],'evidence':'source literal to preserve','pages_one_based':[3]}
  if kind=='CONDITIONAL':p.update(evidence_kind='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE',strict_statutory_capital_tax_certification=False)
  c['capital_tax'][code+'|'+ex]=p
 d=doc('SZ000937','2026-06-11','2026-06-17','0.1','0.100000','2026-06-16');c['documents'].append(d);packets['SZ000937']={'instrument':'SZ000937','distributions':[row(d)]}
 sd=doc('SZ000937','2026-08-27','2026-06-17','0.1','0.1','2026-06-16',name='SZ000937-report.pdf');c['documents'].append(sd)
 c['unresolved_tax']['SZ000937|2026-06-17']={'verified_exempt':False,'strict_tax_admission_resolved':False,'implementation':{'source_file':d['file'],'source_sha256':d['sha256']},'supplement':{'source_file':sd['file'],'source_sha256':sd['sha256']},'original_literal':'do not transform'}
 d=doc('SZ000975','2026-04-17','2026-04-24','0.4804021',rec='2026-04-23');c['documents'].append(d);r=row(d,cash='0.480402',cap='');packets['SZ000975']={'instrument':'SZ000975','distributions':[r]}
 c['cash_overrides']['SZ000975|2026-04-24']={'verified':True,'kind':'PRIMARY_NOTICE_CASH_PRECISION','source_file':d['file'],'source_sha256':d['sha256'],
  'source_row_sha256':dig(r),'expected_vendor_cash_per_share':'0.480402','effective_cash_per_share':'0.4804021','pages_one_based':[1,2,3,4]}
 for code,pub,rec,ex,cash,cap,kind in [('SH603233','2026-10-12','2026-10-16','2026-10-19','0.41','0','NOT_APPLICABLE'),
  ('SH603605','2026-10-12','2026-10-15','2026-10-16','1.18','0','NOT_APPLICABLE'),
  ('SH603596','2026-04-30','2026-05-08','2026-05-11','0.38','0.48','DIRECT'),
  ('SH603606','2026-05-19','2026-05-25','2026-05-26','0.56','0.2','UNRESOLVED_GENERAL_CAPITAL_RESERVE_ONLY'),
  ('SZ002831','2026-05-29','2026-06-03','2026-06-04','0.8038127','0.4019063','PREMIUM_BALANCE_AND_EXPLICIT_CASH_TAX_AMOUNT_CONDITIONAL_INFERENCE')]:
  d=doc(code,pub,ex,cash,cap,rec,kind);notices[code]=d
  if code=='SH603605':d['price_reference_cash_per_share_CNY']='1.17'
  if code=='SZ002831':
   d.update(cash_per_10_original_shares_CNY='8.038127',capital_per_10_original_shares='4.019063',price_reference_cash_per_share_CNY='0.7991573',price_reference_share_change_ratio='0.3995786')
  packets[code]={'instrument':code,'distributions':[] if cap=='0' else [row(d,cash='0.803813' if code=='SZ002831' else None,cap='0.401906' if code=='SZ002831' else None)]}
 old_events=[{'event_id':str(i)} for i in range(378)];old_receipts=[{'event_id':str(i),'instrument':'SH600000','ex_date':'2024-05-20','requires_zero_record_ownership_if_tax_unverified':False} for i in range(378)]
 old_events[0].update(instrument='SH603596',ex_date='2024-05-20',capital_tax_exempt_verified=False)
 old_receipts[0].update(instrument='SH603596',requires_zero_record_ownership_if_tax_unverified=True)
 b={'packets':packets,'cached':cached,'notices':notices,'documents':docs,'old_events':old_events,'old_receipts':old_receipts,'PDF_bytes':pdf}
 # Mirror the two distinct published review schemas, not a caller-selected stronger label.
 notices['SH603605']['capital_tax_evidence_level']='NOT_APPLICABLE_NO_NONCASH'
 notices['SH603596']['capital_tax_evidence_level']='DIRECT_ISSUER_PREMIUM_SOURCE_AND_TRANSFER_NO_TAX_STATEMENT'
 notices['SH603596']['direct_premium_source_and_no_tax_statement']=True
 rootkinds={'SH603605':'NOT_APPLICABLE_CASH_ONLY','SH603596':'DIRECT_PREMIUM_SOURCE_AND_NO_TAX_STATEMENT',
 'SH603606':'UNRESOLVED_NO_PREMIUM_SOURCE_OR_NO_TAX_STATEMENT_IN_ALL5PAGES','SZ002831':'PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE_CANDIDATE_NOT_DIRECT'}
 rootdocs=[]
 for code in rootkinds:
  d=copy.deepcopy(notices[code]);d.pop('capital_tax_evidence_level');d.pop('direct_premium_source_and_no_tax_statement')
  d['capital_tax_evidence_kind']=rootkinds[code]
  if code=='SZ002831':
   d['primary_cash_per10_original_shares_CNY']=d.pop('cash_per_10_original_shares_CNY');d['primary_capital_per10_original_shares']=d.pop('capital_per_10_original_shares')
  rootdocs.append(d)
 b['reviews']={'four_root':{'documents':rootdocs},'four_independent':{'documents':[notices[c] for c in rootkinds],
  'all18_pages_independently_text_extracted_and_visually_reviewed':True,'critical':[],'important':[],'root_content_review_sha256':'a'*64},
  'single_root':{'documents':[notices['SH603233']]},'single_independent':{'verified_primary_fields':copy.deepcopy(notices['SH603233']),
  'primary_pdf_sha256':notices['SH603233']['sha256'],'all4pages_independently_text_extracted_and_visually_reviewed':True,
  'critical':[],'important':[],'root_content_review_sha256':'c'*64},
  'binding_sha256':{'four_root':'a'*64,'four_independent':'b'*64,'single_root':'c'*64,'single_independent':'d'*64}}
 return b

class ProjectionTests(unittest.TestCase):
 def api(self,name):self.assertIsNotNone(m,'projection module missing');self.assertTrue(callable(getattr(m,name,None)),name+' not implemented');return getattr(m,name)
 def project(self,b):return self.api('project_sources')(b)
 def test_final_actual_rights_and_mixed_component_dates(self):
  b=fixture();before=copy.deepcopy(b);p=self.project(b)
  self.assertEqual(len(p['supplementary_distributions']),8);self.assertEqual(len(p['capital_tax']),5)
  self.assertEqual(set(p['unresolved_tax']),{'SH603606|2026-05-26','SZ000937|2026-06-17'})
  s=next(x for x in p['supplementary_distributions'] if x['instrument']=='SH603605');self.assertEqual(s['record']['dividCashPsBeforeTax'],'1.18')
  c=p['component_precision_overrides']['SZ002831|2026-06-04'];self.assertEqual(c['components']['cash_per_share']['effective_per_share'],'0.8038127');self.assertEqual(c['components']['capital_per_share']['effective_per_share'],'0.4019063');self.assertEqual(c['record_date'],'2026-06-03')
  self.assertFalse(p['event_compilation_admitted']);self.assertFalse(p['portfolio_returns_computed']);self.assertEqual(b,before)
 def test_cached_literals_and_original2024_guard_unchanged(self):
  b=fixture();p=self.project(b);old=b['cached']['cache-a']
  self.assertEqual(p['supplementary_distributions'][:6],old['supplementary_distributions']);self.assertEqual(p['cash_overrides'],old['cash_overrides'])
  for k,x in old['capital_tax'].items():self.assertEqual(p['capital_tax'][k],x)
  self.assertEqual(p['unresolved_tax']['SZ000937|2026-06-17'],old['unresolved_tax']['SZ000937|2026-06-17'])
  self.assertFalse(b['old_events'][0]['capital_tax_exempt_verified']);self.assertTrue(b['old_receipts'][0]['requires_zero_record_ownership_if_tax_unverified'])
 def test_duplicate_supplement_inside_one_origin_rejected(self):
  b=fixture();b['cached']['cache-a']['supplementary_distributions'].append(copy.deepcopy(b['cached']['cache-a']['supplementary_distributions'][0]));self.assertRaises(ValueError,self.project,b)
 def test_same_date_vendor_row_rejects_new_income(self):
  b=fixture();s=b['cached']['cache-a']['supplementary_distributions'][0];b['packets'][s['instrument']]['distributions'].append(copy.deepcopy(s['record']));self.assertRaises(ValueError,self.project,b)
 def test_reference_or_proposal_ratios_rejected(self):
  for field,value in [('cash_per_original_share_CNY','0.7991573'),('capital_per_original_share','0.3995786'),('cash_per_10_original_shares_CNY','8')]:
   b=fixture();b['notices']['SZ002831'][field]=value;self.assertRaises(ValueError,self.project,b)
 def test_unknowns_or_conditional_evidence_not_upgraded(self):
  b=fixture();b['notices']['SH603606']['direct_premium_source_and_no_tax_statement']=True;self.assertRaises(ValueError,self.project,b)
  b=fixture();b['notices']['SZ002831']['direct_premium_source_and_no_tax_statement']=True;self.assertRaises(ValueError,self.project,b)
  b=fixture();b['cached']['cache-a']['unresolved_tax']['SZ000937|2026-06-17']['verified_exempt']=True;self.assertRaises(ValueError,self.project,b)
 def test_975_row_digest_mismatch_rejected(self):
  b=fixture();b['packets']['SZ000975']['distributions'][0]['dividCashPsBeforeTax']='0.480403';self.assertRaises(ValueError,self.project,b)
 def test_new_notice_wrong_record_date_rejected(self):
  b=fixture();b['notices']['SH603596']['record_date']='2026-05-11';self.assertRaises(ValueError,self.project,b)
 def test_old2024_guard_cannot_be_erased(self):
  b=fixture();b['old_events'][0]['capital_tax_exempt_verified']=True;self.assertRaises(ValueError,self.project,b)
 def test_changed_pdf_or_unbound_file_rejected_before_copy(self):
  fn=self.api('authenticate_file_map')
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'source.pdf';p.write_bytes(b'%PDF original');fn(Path(d),{'source.pdf':h(b'%PDF original')});p.write_bytes(b'%PDF changed');self.assertRaises(ValueError,fn,Path(d),{'source.pdf':h(b'%PDF original')})
   self.assertRaises(ValueError,fn,Path(d),{'../outside.pdf':'0'*64})
 def test_http_semantics_not_only_coherent_rehash(self):
  fn=self.api('check_http_chain');identity={'source':'CNINFO_HTTP','url':'https://example.invalid/registered.PDF','payload':None,'request_sha256':'1'*64};key=dig(identity);pdf=b'%PDF synthetic'
  reserved={'identity_sha256':key,'attempt':1};rh=dig(reserved)
  payload={'fields':['http_response'],'rows':[{'status':200,'final_url':identity['url'],'body_complete':True,'body_truncated':False,'read_error_type':None,'read_error':None,'body_base64':base64.b64encode(pdf).decode()}]}
  response={'identity_sha256':key,'reservation_sha256':rh,'status':'CAPTURED','payload':payload,'payload_sha256':dig(payload)}
  fn(identity,reserved,response,pdf,identity,rh)
  for field,value in [('final_url',identity['url']+'?wrong'),('body_complete',False),('body_base64',base64.b64encode(pdf+b'x').decode())]:
   changed=copy.deepcopy(response);changed['payload']['rows'][0][field]=value;changed['payload_sha256']=dig(changed['payload']);self.assertRaises(ValueError,fn,identity,reserved,changed,pdf,identity,rh)
 def test_byte_reuse_does_not_invent_http_receipt(self):
  b=fixture();p=self.project(b);doc=next(d for d in p['documents'] if d['instrument']=='SH601128');self.assertNotIn('pdf_receipt',doc)

 def primary_fixture(self,root,route='HTTP'):
  pdf=b'%PDF authenticated original';d={'instrument':'SH603605','file':'notice.pdf','sha256':h(pdf),'day':'2026-10-12','url':'https://example.invalid/notice.PDF'}
  def put(name,value):
   p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value if isinstance(value,bytes) else json.dumps(value,sort_keys=True,separators=(',',':')).encode());return h(p.read_bytes())
  bindings={};bindings['capture/notice.pdf']=put('capture/notice.pdf',pdf)
  spec={'route':route,'pdf_file':'capture/notice.pdf','pdf_sha256':h(pdf),'source_manifest_file':'capture/manifest.json','source_document_file':'notice.pdf',
   'content_review_refs':[{'root':'base','file':'review.json'}]}
  if route=='HTTP':
   identity={'source':'CNINFO_HTTP','url':d['url'],'payload':None,'request_sha256':'a'*64};key=dig(identity);rh=put('capture/queries/r.json',{'identity_sha256':key,'attempt':1})
   payload={'fields':['http_response'],'rows':[{'status':200,'final_url':d['url'],'body_complete':True,'body_truncated':False,'read_error_type':None,'read_error':None,'body_base64':base64.b64encode(pdf).decode()}]}
   response={'identity_sha256':key,'reservation_sha256':rh,'status':'CAPTURED','payload':payload,'payload_sha256':dig(payload)}
   receipt={}
   for kind,name,obj in [('request','queries/q.json',identity),('reserved','queries/r.json',{'identity_sha256':key,'attempt':1}),('response','queries/s.json',response)]:
    full='capture/'+name;bindings[full]=put(full,obj);receipt[kind+'_file']=name;receipt[kind+'_sha256']=bindings[full]
   d['pdf_receipt']=receipt;spec.update(capture_root='capture',expected_identity=identity)
  else:d['pdf_receipt']=None
  bindings['capture/manifest.json']=put('capture/manifest.json',{'documents':[d]});bindings['review.json']=put('review.json',{'documents':[d],'reviewed':True})
  return spec,bindings,d
 def test_primary_chain_binds_registered_manifest_PDF_and_review(self):
  fn=self.api('authenticate_primary_evidence')
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);spec,bindings,d=self.primary_fixture(root);result=fn(root,root,spec,bindings,{})
   self.assertEqual(result['document'],d);self.assertTrue(result['HTTP_decoded_body_matches_PDF']);self.assertFalse(result['historical_arrival_certified'])
   bad=copy.deepcopy(spec);bad['expected_identity']['url']+='?wrong';self.assertRaises(ValueError,fn,root,root,bad,bindings,{})
 def test_primary_review_reference_cannot_be_unbound(self):
  fn=self.api('authenticate_primary_evidence')
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);spec,bindings,d=self.primary_fixture(root);del bindings['review.json'];self.assertRaises(ValueError,fn,root,root,spec,bindings,{})
 def test_reused_primary_keeps_original_missing_HTTP_receipt(self):
  fn=self.api('authenticate_primary_evidence')
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);spec,bindings,d=self.primary_fixture(root,'REVIEWED_BYTE_REUSE');result=fn(root,root,spec,bindings,{})
   self.assertIsNone(result['document']['pdf_receipt']);self.assertFalse(result['HTTP_decoded_body_matches_PDF']);self.assertEqual(result['chain_kind'],'AUTHENTICATED_REVIEWED_BYTE_REUSE_ONLY')
 def test_copy_output_preserves_original_bytes_and_metadata(self):
  fn=self.api('write_projection');b=fixture();proposal=self.project(b)
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);sources=root/'sources';sources.mkdir();paths={}
   for name,pdf in b['PDF_bytes'].items():p=sources/name;p.write_bytes(pdf);paths[name]=p
   output=root/'price-delay-horizon-corporate-reviewed-20261021';fn(output,proposal,paths)
   self.assertEqual(json.loads((output/'reviewed-manifest.json').read_text()),proposal)
   for d in proposal['documents']:self.assertEqual((output/d['file']).read_bytes(),paths[d['file']].read_bytes())
   self.assertRaises(ValueError,fn,output,proposal,paths)
 def test_changed_copy_source_fails_before_output_creation(self):
  fn=self.api('write_projection');b=fixture();proposal=self.project(b)
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);sources=root/'sources';sources.mkdir();paths={}
   for name,pdf in b['PDF_bytes'].items():p=sources/name;p.write_bytes(pdf);paths[name]=p
   first=proposal['documents'][0]['file'];paths[first].write_bytes(b'%PDF changed')
   out=root/'price-delay-horizon-corporate-reviewed-20261021';self.assertRaises(ValueError,fn,out,proposal,paths);self.assertFalse(out.exists())

 def test_output_document_day_is_canonical_publication_not_signature(self):
  b=fixture()
  for d in b['notices'].values():d.pop('day');d['signature_day']='2026-01-01'
  p=self.project(b);d=next(d for d in p['documents'] if d['instrument']=='SZ002831')
  self.assertIn('day',d);self.assertEqual(d['day'],'2026-05-29');self.assertEqual(d['signature_day'],'2026-01-01')
  self.assertNotIn('day',b['notices']['SZ002831'])
 def test_writer_rejects_unknown_or_conditional_upgrade_before_creation(self):
  fn=self.api('write_projection');b=fixture();original=self.project(b)
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);sources=root/'sources';sources.mkdir();paths={}
   for name,pdf in b['PDF_bytes'].items():p=sources/name;p.write_bytes(pdf);paths[name]=p
   for label in ('unknown','conditional'):
    proposal=copy.deepcopy(original)
    if label=='unknown':proposal['unresolved_tax']['SZ000937|2026-06-17']['verified_exempt']=True
    else:proposal['capital_tax']['SZ002831|2026-06-04']['evidence_kind']='DIRECT_ISSUER_NO_TAX'
    output=root/'price-delay-horizon-corporate-reviewed-20261021';self.assertRaises(ValueError,fn,output,proposal,paths);self.assertFalse(output.exists())

 def test_canonical_mapping_binds_two_distinct_review_schemas(self):
  fn=self.api('canonical_reviewed_notices');b=fixture();notices=fn(b['reviews']);d=notices['SZ002831']
  self.assertEqual(d['cash_per_10_original_shares_CNY'],'8.038127');self.assertFalse(d['direct_premium_source_and_no_tax_statement'])
  self.assertEqual(d['review_field_mapping']['per10_cash_root_field'],'primary_cash_per10_original_shares_CNY')
  self.assertEqual(d['review_field_mapping']['per10_cash_independent_field'],'cash_per_10_original_shares_CNY')
 def test_root_conditional_or_per10_cannot_be_normalized_upwards(self):
  fn=self.api('canonical_reviewed_notices');b=fixture();d=next(d for d in b['reviews']['four_root']['documents'] if d['instrument']=='SZ002831')
  d['capital_tax_evidence_kind']='DIRECT_PREMIUM_SOURCE_AND_NO_TAX_STATEMENT';self.assertRaises(ValueError,fn,b['reviews'])
  b=fixture();d=next(d for d in b['reviews']['four_root']['documents'] if d['instrument']=='SZ002831');d['primary_cash_per10_original_shares_CNY']='8';self.assertRaises(ValueError,fn,b['reviews'])

if __name__=='__main__':unittest.main(verbosity=2)
