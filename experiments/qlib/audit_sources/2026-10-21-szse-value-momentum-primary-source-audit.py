"""Stdlib audit of six original PDFs and two bounded HTTP journals; content separate."""
import argparse,base64,copy,hashlib,json,re
from pathlib import Path
from datetime import datetime
if not __debug__:raise RuntimeError('Assertions must stay enabled')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
FRESH=[{'instrument':'SZ002508','day':'2024-01-03','url':'https://static.cninfo.com.cn/finalpage/2024-01-03/1218790856.PDF','file':'SZ002508-2024-01-03.pdf'},
 {'instrument':'SZ001389','day':'2024-04-01','url':'https://static.cninfo.com.cn/finalpage/2024-04-01/1219474753.PDF','file':'SZ001389-2024-04-01.pdf'}]
REUSE=['SZ002155-2025-06-07.pdf','SZ002837-2024-05-18.pdf','SZ002837-2025-05-23.pdf','SZ002984-2024-04-12.pdf']
def identity_check(v,requestsha):
 assert set(v)=={'source','url','payload','primary_request_sha256'} and v['source']=='CNINFO_HTTP' and v['payload'] is None
 assert v['primary_request_sha256']==requestsha and v['url'] in {d['url'] for d in FRESH}
def decoded_body(response,url):
 assert response['status']=='CAPTURED' and response['payload_sha256']==digest(response['payload'])
 p=response['payload'];assert p['fields']==['http_response'] and len(p['rows'])==1
 w=p['rows'][0];body=base64.b64decode(w['body_base64'],validate=True)
 assert w['status']==200 and w['final_url']==url and w['body_complete'] is True and w['body_truncated'] is False
 assert w['read_error_type'] is None and w['read_error'] is None and len(body)<=10485760 and body.startswith(b'%PDF')
 return body,w

def preflight(base,repo,requestfile,expected):
 assert sha(requestfile)==expected;r=read(requestfile)
 assert r['status']=='FROZEN_VALUE_MOMENTUM_TWO_PRIMARY_ORIGINALS' and r['candidate']=='szse_value_momentum_equal'
 assert r['fresh_documents']==FRESH and [d['file'] for d in r['reuse_documents']]==REUSE
 assert r['maximum_new_HTTP_reservations']==2 and r['max_attempts_per_identity']==1 and r['accepted_source_cutoff']=='2025-12-31'
 for flag in ('source_admitted_for_account_replay','portfolio_returns_computed','new_2026_market_queries'):assert r[flag] is False
 for field,parent in (('method_code_sha256',repo),('public_inputs_sha256',repo),('local_inputs_sha256',base)):
  for f,h in r[field].items():assert not Path(f).is_absolute() and '..' not in Path(f).parts and sha(parent/f)==h,(field,f)
 old=base/'budgeted-residual-corporate-reviewed-20261021';review=read(old/'reviewed-manifest.json');original_capture=base/'budgeted-residual-corporate-notices-20261021'
 assert sha(original_capture/'manifest.json')==review['capture_manifest_sha256']
 assert sha(base/'budgeted-residual-corporate-capture-audit-20261021.json')==review['capture_audit_sha256']
 raw=base/'szse-value-momentum-raw-dev-20261021';rawm=read(raw/'manifest.json');inherited=[]
 for d in r['reuse_documents']:
  assert d in review['documents'] and sha(old/d['file'])==d['sha256'] and (old/d['file']).read_bytes().startswith(b'%PDF')
  assert (old/d['file']).read_bytes()==(original_capture/d['file']).read_bytes()
  receipt=d['HTTP_pdf_receipt'];folder=original_capture/Path(receipt['request_file']).parent
  for prefix,name in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')):
   assert receipt[prefix+'_file']==str((folder/name).relative_to(original_capture)) and receipt[prefix+'_sha256']==sha(folder/name)
  identity=read(folder/'request.json');reserve=read(folder/'reserved-1.json');response=read(folder/'response-1.json')
  assert folder.name==digest(identity)==reserve['identity_sha256']==response['identity_sha256']
  assert reserve['attempt']==1 and response['reservation_sha256']==sha(folder/'reserved-1.json')
  assert identity['source']=='CNINFO_HTTP' and identity['url']==d['url'] and identity['payload'] is None
  body,_=decoded_body(response,d['url']);assert body==(old/d['file']).read_bytes()
  components=[x for x in review['distribution_component_reviews'] if x['file']==d['file']];assert len(components)==1;c=components[0]
  key=c['case_id'];assert key.startswith(d['instrument']+'|') and c['sha256']==d['sha256']
  proof=review['capital_tax'][key]
  assert proof['source_file']==d['file'] and proof['source_sha256']==d['sha256'] and proof['evidence_kind']=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE'
  assert c['capital_tax_review']=='PREMIUM_SOURCE_PLUS_EXPLICIT_CASH_ONLY_TAX_EXAMPLES_INFERENCE' and c['price_reference_not_used_as_entitlement'] is True
  packetfile=raw/'codes'/(d['instrument']+'.json');assert sha(packetfile)==rawm['per_code_sha256'][d['instrument']]==c['original_source_packet_sha256']
  row=[row for row in read(packetfile)['distributions'] if row['dividOperateDate']==key.split('|')[1]];assert len(row)==1;row=row[0]
  for src,field in (('cash_per_original_share','dividCashPsBeforeTax'),('stock_per_original_share','dividStocksPs'),('capital_per_original_share','dividReserveToStockPs'),('record_date','dividRegistDate'),('ex_date','dividOperateDate'),('cash_payment_date','dividPayDate'),('capital_listing_date','dividStockMarketDate')):assert c[src]==row[field]
  inherited.append({'case_id':key,'file':d['file'],'sha256':d['sha256'],'component_review_unchanged':c,'original_capital_tax_proof_unchanged':proof,
   'new_strict_statutory_exemption_certification':False,'scope':'Event-specific ordinary unrestricted investor inference retained; no broader tax or original-arrival certification'})
 return r,old,review,inherited

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('capture-dir','source-root','repo-root','request','expected-request-sha256','output'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv)
 root=Path(a.capture_dir);base=Path(a.source_root);repo=Path(a.repo_root);requestfile=Path(a.request);out=Path(a.output)
 assert not out.exists();r,old,review,inherited=preflight(base,repo,requestfile,a.expected_request_sha256)
 if a.preflight_only:print('Independent preflight:4 originalPDFs/priorHTTPchains and inference labels authenticated; no output/HTTP');return 0
 m=read(root/'manifest.json');assert m['status']=='VALUE_MOMENTUM_PRIMARY_CAPTURE_REVIEW_SEPARATE' and m['request_sha256']==sha(requestfile)
 assert (root/'request.json').read_bytes()==requestfile.read_bytes() and m['documents']==read(root/'progress.json') and m['errors']==read(root/'errors.json')
 allowed=set(REUSE)|{d['file'] for d in FRESH};assert not set(m['documents'])&set(m['errors'])
 assert sorted(set(m['documents'])|set(m['errors'])|set(m['pending_files']))==sorted(allowed)
 for flag in ('documents_financially_reviewed','listing_boundary_verified','supplementary_distribution_verified','raw_source_admitted_for_account_replay','investment_rules_changed','portfolio_returns_computed','new_2026_market_queries'):assert m[flag] is False
 chains={};outcomes=[]
 for folder in sorted((root/'queries').iterdir()) if (root/'queries').exists() else []:
  assert sorted(f.name for f in folder.iterdir())==['request.json','reserved-1.json','response-1.json']
  identity=read(folder/'request.json');identity_check(identity,sha(requestfile));reserve=read(folder/'reserved-1.json');response=read(folder/'response-1.json')
  assert folder.name==digest(identity)==reserve['identity_sha256']==response['identity_sha256'] and reserve['attempt']==1
  assert datetime.fromisoformat(reserve['reserved_at_utc']).utcoffset().total_seconds()==0 and response['reservation_sha256']==sha(folder/'reserved-1.json')
  assert identity['url'] not in chains;chains[identity['url']]=(folder,response)
  assert response['status'] in ('CAPTURED','SOURCE_ERROR')
  if response['status']=='CAPTURED':
   assert response['payload_sha256']==digest(response['payload']);payload=response['payload'];assert payload['fields']==['http_response'] and len(payload['rows'])==1
   w=payload['rows'][0];data=base64.b64decode(w['body_base64'],validate=True)
   outcome={k:v for k,v in w.items() if k!='body_base64'}|{'observed_body_bytes':len(data),'body_sha256':hashlib.sha256(data).hexdigest()}
  else:outcome={k:response[k] for k in ('error_type','error')}
  outcomes.append({'identity':identity,'HTTP_outcome':outcome,'response_sha256':sha(folder/'response-1.json')})
 assert len(chains)==len(list(root.rglob('reserved-*.json')))==m['HTTP_query_reservations']<=2 and m['maximum_HTTP_query_reservations']==2
 verified=[];fresh_responses={}
 for name,doc in m['documents'].items():
  assert Path(name).name==name and doc['file']==name and sha(root/name)==doc['sha256'] and (root/name).read_bytes().startswith(b'%PDF')
  if name in REUSE:
   original=next(d for d in r['reuse_documents'] if d['file']==name)
   assert doc=={**original,'capture_route':'BYTE_IDENTICAL_REVIEWED_PRIMARY_REUSE'} and (root/name).read_bytes()==(old/name).read_bytes()
  else:
   registered=next(d for d in FRESH if d['file']==name);assert {k:doc[k] for k in registered}==registered and doc['capture_route']=='JOURNALED_ORIGINAL_PRIMARY_HTTP'
   folder,response=chains[doc['url']];body,w=decoded_body(response,doc['url']);assert body==(root/name).read_bytes()
   for prefix,f in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')):
    assert doc['HTTP_pdf_receipt'][prefix+'_file']==str((folder/f).relative_to(root)) and doc['HTTP_pdf_receipt'][prefix+'_sha256']==sha(folder/f)
   fresh_responses[name]=(response,doc['url']);assert set(doc)==set(registered)|{'sha256','HTTP_pdf_receipt','capture_route'}
  verified.append({'file':name,'instrument':doc['instrument'],'registered_document_day':doc['day'],'sha256':doc['sha256'],'bytes':(root/name).stat().st_size,'capture_route':doc['capture_route'],'byte_and_identity_chain_verified':True})
 errors={}
 for name,h in m['errors'].items():
  f=root/(name+'.error.json');assert sha(f)==h;v=read(f);assert v['file']==name and v['response_retained'] is True;errors[name]={'sha256':h,'record':v}
 complete=len(verified)==6 and not errors and not m['pending_files']
 if complete:assert len(chains)==2 and len(fresh_responses)==2
 negatives={}
 if fresh_responses:
  response,url=next(iter(fresh_responses.values()))
  for mode in ('redirect','truncated','incomplete','read_error','wrong_magic'):
   changed=copy.deepcopy(response);w=changed['payload']['rows'][0]
   if mode=='redirect':w['final_url']=url+'?unregistered'
   elif mode=='truncated':w['body_truncated']=True
   elif mode=='incomplete':w['body_complete']=False
   elif mode=='read_error':w['read_error_type']='ConnectionResetError';w['read_error']='retained partial'
   else:w['body_base64']=base64.b64encode(b'<html>not PDF</html>').decode()
   changed['payload_sha256']=digest(changed['payload'])
   try:decoded_body(changed,url)
   except AssertionError:negatives[mode]=True
   else:raise AssertionError('semantic HTTP mutation accepted:'+mode)
  changed={'source':'CNINFO_HTTP','url':'https://static.cninfo.com.cn/finalpage/2026-01-01/999999.PDF','payload':None,'primary_request_sha256':sha(requestfile)}
  try:identity_check(changed,sha(requestfile))
  except AssertionError:negatives['unregistered_future_URL']=True
  else:raise AssertionError('unregistered future URL accepted')
 for d in r['reuse_documents']:assert sha(old/d['file'])==d['sha256']
 assert sha(requestfile)==a.expected_request_sha256
 artifacts={str(f.relative_to(root)):sha(f) for f in root.rglob('*') if f.is_file() and f.name!='capture.lock'}
 result={'status':'SIX_PRIMARY_BYTE_IDENTITY_CHAINS_AUDITED_CONTENT_REVIEW_SEPARATE','audit_code_sha256':sha(__file__),'request_sha256':sha(requestfile),'capture_manifest_sha256':sha(root/'manifest.json'),
  'capture_complete':complete,'documents':verified,'reused_originals':len([v for v in verified if v['capture_route']=='BYTE_IDENTICAL_REVIEWED_PRIMARY_REUSE']),
  'new_exact_PDF_HTTP_queries':len(chains),'maximum_HTTP_reservations':2,'new_announcement_API_or_market_queries':0,'HTTP_outcomes_and_errors_retained':outcomes,
  'capture_artifact_sha256':artifacts,'errors':errors,'pending_files':m['pending_files'],'prior_four_event_specific_inferences_unchanged':inherited,
  'semantic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,'financial_content_review_complete':False,'listing_boundary_verified':False,'supplementary_distribution_verified':False,
  'new_strict_statutory_exemption_certification':False,'raw_source_admitted_for_account_replay':False,'portfolio_returns_computed':False,'new_source_queries_performed':0,'new_2026_market_queries':False,
  'unselected_2026_notice_opened_or_used':False,'objective_achieved':False,
  'content_review_required':['Inspect complete relevant pages for issuer identity, announcement/signature/path dates, ordinary registered shareholder amounts versus adjusted price-reference averages, record/ex/pay/list dates and tax wording.',
   'SZ002508 special distribution must use the issuer stated cash entitlement, never the observed0.50 reference gap.',
   'SZ001389 lifecycle boundary must come from explicit original listing text; first raw bar/factor and incomplete calendar prove no IPO/listing classification.',
   'Carry all four inherited premium-source plus cash-tax-example inference labels, ordinary investor scope and SZ0028372024 publication metadata caveat forward; do not promote them to broader statutory proof.']}
 with out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print('Independent primary capture audit',len(verified),'PDFs,',len(chains),'newHTTPchains; content/admission separate')
 return 0
if __name__=='__main__':raise SystemExit(main())
