"""Independent stdlib verification of saved source projection, no production imports."""
import base64,copy,hashlib,json,subprocess
from collections import Counter
from decimal import Decimal,ROUND_DOWN
from fractions import Fraction
from pathlib import Path
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015');R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');O=B/'price-delay-horizon-corporate-reviewed-20261021'
REQ='4b2c8860037ee7b75c0d63f721726f9092a83137d8353f90a6eed0c0c2546998';MAN='51c236c980a154048f147dd8ee9f7053763e71a0fda769be10f94331aee3cb07';SUMMARY='7285f0abe2cbe5e80b70a981f0b89a3d9600d127a6b703cfdf9923d19e594d99'
OUT=Path('/tmp/price-delay-horizon-proof-projection-output-review-20261021.json')
CACHES=['low-beta60-corporate-reviewed-horizon-20261021/reviewed-manifest.json','low-beta60-corporate-reviewed-2026-20261021/reviewed-manifest.json','szse-value-momentum-full-reviewed-proofs-20261021.json','szse-value-full-corporate-notices-20261017/reviewed-manifest.json','return-family-corporate-notices-20261017/reviewed-manifest.json','reversal-full-corporate-notices-20261017/reviewed-manifest.json']
CASH=['SH601598|2026-10-20','SH601918|2026-02-06','SH601966|2026-06-24','SZ002608|2026-10-19','SZ002756|2026-10-20','SZ002812|2026-10-20'];CAP=['SH601128|2026-06-09','SH603737|2026-06-01','SZ002595|2026-05-11'];MIXED='SZ002831|2026-06-04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def safe(root,name):
 p=(root/name).resolve();assert not Path(name).is_absolute() and '..' not in Path(name).parts and p.is_relative_to(root.resolve());return p

def check_HTTP(q,a,v,pdf,expected,ash):
 assert q==expected and q['source']=='CNINFO_HTTP' and q['payload'] is None
 k=digest(q);assert a['identity_sha256']==k and type(a['attempt']) is int and a['attempt']==1
 assert v['identity_sha256']==k and v['reservation_sha256']==ash and v['status']=='CAPTURED'
 p=v['payload'];assert digest(p)==v['payload_sha256'] and p['fields']==['http_response'] and len(p['rows'])==1
 x=p['rows'][0];assert type(x['status']) is int and x['status']==200 and x['final_url']==q['url'] and x['body_complete'] is True and x['body_truncated'] is False and x['read_error_type'] is None and x['read_error'] is None
 body=base64.b64decode(x['body_base64'],validate=True);assert body==pdf and body.startswith(b'%PDF') and len(body)<=10485760

def has_document(value,doc):
 if isinstance(value,list):return any(has_document(x,doc) for x in value)
 if isinstance(value,dict):
  p=value.get('pdf_sha256')
  if isinstance(p,dict) and p.get(Path(doc['file']).stem)==doc['sha256']:return True
  if p==doc['sha256'] and value.get('sourcefacts',{}).get('instrument')==doc['instrument']:return True
  if value.get('sha256')==doc['sha256'] and isinstance(value.get('file'),str) and Path(value['file']).name==doc['file'] and value.get('instrument',doc['instrument'])==doc['instrument']:return True
  return any(has_document(x,doc) for x in value.values())
 return False

def primary_chains(plan):
 chains={};http=0;reuse=0
 for name,spec in plan['primary_evidence'].items():
  bound={}
  def boundfile(kind,relative):
   root=B if kind=='base' else R;mapping=plan['primary_files_sha256'] if kind=='base' else plan['public_evidence_sha256'];assert relative in mapping
   p=safe(root,relative);assert sha(p)==mapping[relative];bound[str(p)]=mapping[relative];return p
  pp=boundfile('base',spec['pdf_file']);pdf=pp.read_bytes();assert sha(pp)==spec['pdf_sha256'] and pdf.startswith(b'%PDF')
  sm=read(boundfile('base',spec['source_manifest_file']));docs=sm['documents'];docs=list(docs.values()) if isinstance(docs,dict) else docs
  found=[d for d in docs if d.get('file')==name and d.get('sha256')==spec['pdf_sha256']];assert len(found)==1;doc=found[0]
  assert spec['content_review_refs']
  for ref in spec['content_review_refs']:assert has_document(read(boundfile(ref['root'],ref['file'])),doc)
  if spec['route']=='HTTP':
   rec=doc['pdf_receipt'];parts={}
   for kind in ['request','reserved','response']:
    p=boundfile('base',spec['capture_root']+'/'+rec[kind+'_file']);assert sha(p)==rec[kind+'_sha256'];parts[kind]=read(p)
   assert spec['expected_identity']['url']==doc['url'];check_HTTP(parts['request'],parts['reserved'],parts['response'],pdf,spec['expected_identity'],rec['reserved_sha256'])
   kind='ORIGINAL_REQUEST_RESERVATION_DECODED_HTTP_BODY_PDF';body=True;http+=1
  else:
   assert spec['route']=='REVIEWED_BYTE_REUSE' and 'capture_root' not in spec and 'expected_identity' not in spec
   kind='AUTHENTICATED_REVIEWED_BYTE_REUSE_ONLY';body=False;reuse+=1
  chains[name]={'document':doc,'source_PDF_file':str(pp),'source_PDF_sha256':spec['pdf_sha256'],'chain_kind':kind,'HTTP_decoded_body_matches_PDF':body,'HTTP_wire_transport_certified':False,'historical_arrival_certified':False,'authenticated_original_files':bound,'new_source_query':False,'financial_admission':False}
 assert (http,reuse)==(14,3)
 return chains

def independent_notices():
 frootpath=R/'experiments/qlib/price-delay-horizon-four-primary-content-review.json';findpath=R/'experiments/qlib/price-delay-horizon-four-primary-independent-review.json';srootpath=R/'experiments/qlib/price-delay-horizon-single-primary-content-review.json';sindpath=R/'experiments/qlib/price-delay-horizon-single-primary-independent-review.json'
 fr,fi,sr,si=map(read,[frootpath,findpath,srootpath,sindpath]);assert fi['root_content_review_sha256']==sha(frootpath) and si['root_content_review_sha256']==sha(srootpath)
 assert not fi['critical'] and not fi['important'] and fi['all18_pages_independently_text_extracted_and_visually_reviewed'] is True
 assert not si['critical'] and not si['important'] and si['all4pages_independently_text_extracted_and_visually_reviewed'] is True
 roots={x['instrument']:x for x in fr['documents']};out={}
 labels={'SH603605':('NOT_APPLICABLE_CASH_ONLY','NOT_APPLICABLE_NO_NONCASH',False),'SH603596':('DIRECT_PREMIUM_SOURCE_AND_NO_TAX_STATEMENT','DIRECT_ISSUER_PREMIUM_SOURCE_AND_TRANSFER_NO_TAX_STATEMENT',True),'SH603606':('UNRESOLVED_NO_PREMIUM_SOURCE_OR_NO_TAX_STATEMENT_IN_ALL5PAGES','UNRESOLVED_GENERAL_CAPITAL_RESERVE_ONLY',False),'SZ002831':('PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE_CANDIDATE_NOT_DIRECT','PREMIUM_BALANCE_AND_EXPLICIT_CASH_TAX_AMOUNT_CONDITIONAL_INFERENCE',False)}
 for doc in fi['documents']:
  code=doc['instrument'];a=roots[code];rk,ik,direct=labels[code]
  for key in ['instrument','file','sha256','publication_day','record_date','ex_date','cash_payment_date','stock_listing_date','cash_per_original_share_CNY','capital_per_original_share','stock_per_original_share']:assert a.get(key)==doc.get(key)
  assert a['capital_tax_evidence_kind']==rk and doc['capital_tax_evidence_level']==ik and doc['direct_premium_source_and_no_tax_statement'] is direct
  d=copy.deepcopy(doc);mapping={'root_tax_field':'capital_tax_evidence_kind','root_tax_literal':rk,'independent_tax_field':'capital_tax_evidence_level','independent_tax_literal':ik,'independent_direct_statement_field':'direct_premium_source_and_no_tax_statement','independent_direct_literal':direct}
  if code=='SZ002831':
   assert a['primary_cash_per10_original_shares_CNY']==d['cash_per_10_original_shares_CNY']=='8.038127' and a['primary_capital_per10_original_shares']==d['capital_per_10_original_shares']=='4.019063'
   mapping.update(per10_cash_root_field='primary_cash_per10_original_shares_CNY',per10_cash_independent_field='cash_per_10_original_shares_CNY',per10_capital_root_field='primary_capital_per10_original_shares',per10_capital_independent_field='capital_per_10_original_shares')
  d['review_field_mapping']=mapping;d['review_provenance']={'root_review_sha256':sha(frootpath),'independent_review_sha256':sha(findpath),'root_document_literal_sha256':digest(a),'independent_document_literal_sha256':digest(doc)};out[code]=d
 d=copy.deepcopy(sr['documents'][0]);assert d['instrument']=='SH603233' and si['primary_pdf_sha256']==d['sha256']
 for k in ['instrument','publication_day','record_date','ex_date','cash_payment_date','cash_per_original_share_CNY','stock_per_original_share','capital_per_original_share']:assert d[k]==si['verified_primary_fields'][k]
 d['review_field_mapping']={'economic_fields_compared_to':'verified_primary_fields','root_pdf_sha_field':'documents[0].sha256','independent_pdf_sha_field':'primary_pdf_sha256'};d['review_provenance']={'root_review_sha256':sha(srootpath),'independent_review_sha256':sha(sindpath),'root_document_literal_sha256':digest(sr['documents'][0]),'independent_verified_fields_literal_sha256':digest(si['verified_primary_fields'])};out['SH603233']=d
 return out

def expected_proofs(plan,chains):
 caches={n:read(B/n) for n in CACHES};notices=independent_notices();documents={}
 for proposal in caches.values():
  v=proposal['documents'];v=list(v.values()) if isinstance(v,dict) else v
  for d in v:documents.setdefault(d['file'],copy.deepcopy(d))
 for n,chain in chains.items():
  d=copy.deepcopy(documents.get(n,chain['document']))
  if d['instrument'] in notices:d.update(copy.deepcopy(notices[d['instrument']]))
  d['day']=d.get('publication_day',d.get('day'));d['source_evidence_chain']=chain;documents[n]=d
 def select(field,keys):
  found={};origins={}
  for origin,source in caches.items():
   v=source.get(field,{} if field!='supplementary_distributions' else [])
   if isinstance(v,list):v={x['instrument']+'|'+x['record']['dividOperateDate']:x for x in v}
   for key,item in v.items():
    if key not in keys:continue
    assert key not in found or found[key]==item;found[key]=copy.deepcopy(item);origins.setdefault(key,[]).append(origin)
  assert set(found)==set(keys);return found,origins
 cash,co=select('supplementary_distributions',CASH);capital,ca=select('capital_tax',CAP);unknown,un=select('unresolved_tax',{'SZ000937|2026-06-17'});precision,po=select('cash_overrides',{'SZ000975|2026-04-24'})
 supplements=[cash[k] for k in CASH]
 for code in ['SH603233','SH603605']:
  d=notices[code];row={'code':code[:2].lower()+'.'+code[2:],'dividPlanDate':d['publication_day'],'dividRegistDate':d['record_date'],'dividOperateDate':d['ex_date'],'dividPayDate':d['cash_payment_date'],'dividStockMarketDate':'','dividCashPsBeforeTax':d['cash_per_original_share_CNY'],'dividStocksPs':'0','dividReserveToStockPs':'0','dividCashStock':'PRIMARY_CASH_ONLY_NOTICE'}
  supplements.append({'instrument':code,'record':row,'source_file':d['file'],'source_sha256':d['sha256'],'primary_pages':d['primary_pages'],'record_origin':'Separately authenticated issuer implementation notice, not a vendor rewrite or factor-derived payment','reference_price_cash_per_share_not_entitlement':d.get('price_reference_cash_per_share_CNY')})
 d=notices['SH603596'];capital['SH603596|2026-05-11']={'verified_exempt':True,'source_file':d['file'],'source_sha256':d['sha256'],'pages_one_based':d['field_pages']['premium_source_and_transfer_no_tax'],'evidence_kind':'DIRECT_ISSUER_PREMIUM_SOURCE_AND_TRANSFER_NO_TAX_STATEMENT','strict_statutory_capital_tax_certification':False,'evidence':'Original issuer notice explicitly identifies share-premium source and this event transfer no-tax; this2026 event only, not2024.'}
 d=notices['SZ002831'];capital[MIXED]={'verified_exempt':True,'source_file':d['file'],'source_sha256':d['sha256'],'pages_one_based':[2,3],'evidence_kind':'PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE','strict_statutory_capital_tax_certification':False,'issuer_explicit_transfer_no_tax_statement':False,'evidence':'Conditional inference from premium-balance ceiling and separately published rounded cash-only tax examples; no exclusive premium tracing or statutory certificate.','tax_examples':{'cash_per_ten':'8.038127','one_month_tax_per_ten':'1.607625','one_year_tax_per_ten':'0.803813','printed_examples_rounded':True}}
 d=notices['SH603606'];unknown['SH603606|2026-05-26']={'verified_exempt':False,'strict_tax_admission_resolved':False,'issuer_explicit_no_tax_statement':False,'implementation':{'source_file':d['file'],'source_sha256':d['sha256'],'primary_pages':d['primary_pages'],'cash_per_original_share':d['cash_per_original_share_CNY'],'capital_per_original_share':d['capital_per_original_share'],'record_day':d['record_date'],'ex_pay_list_day':d['ex_date']},'evidence_assessment':'All original notice pages show generic reserve only; no premium source/no-tax statement. Cash-tax examples alone do not resolve capital tax.','account_behavior_required':'Fail before mutation at exdate for any positive recorded inventory; zero record ownership only, never alter targets to bypass.'}
 rawroot=B/'price-delay-raw-horizon-v2-20261021';rawm=read(rawroot/'manifest.json');packet_cache={}
 def packet(code):
  if code not in packet_cache:
   p=rawroot/'codes'/(code+'.json');assert sha(p)==rawm['per_code_sha256'][code];packet_cache[code]=read(p)
  return packet_cache[code]
 def vendor(key):
  code,day=key.split('|');v=[x for x in packet(code)['distributions'] if x['dividOperateDate']==day];assert len(v)==1;return v[0]
 for s in supplements:assert not any(x['dividOperateDate']==s['record']['dividOperateDate'] for x in packet(s['instrument'])['distributions'])
 for key in capital:
  row=vendor(key);doc=documents[capital[key]['source_file']];assert row['dividPlanDate']==doc['day'] and Decimal(row['dividReserveToStockPs'])>0
 d=notices['SZ002831'];row=vendor(MIXED);comps={}
 for attr,field,perfield,dfield in [('cash_per_share','dividCashPsBeforeTax','cash_per_10_original_shares_CNY','cash_per_original_share_CNY'),('capital_per_share','dividReserveToStockPs','capital_per_10_original_shares','capital_per_original_share')]:
  raw=row[field];effective=d[dfield];per10=d[perfield];assert Fraction(effective)==Fraction(per10)/10 and 0<abs(Fraction(raw)-Fraction(effective))<=Fraction(1,2000000)
  comps[attr]={'expected_vendor_per_share':raw,'primary_per10_original_shares':per10,'effective_per_share':effective}
 for field,name in [('dividPlanDate','publication_day'),('dividRegistDate','record_date'),('dividOperateDate','ex_date'),('dividPayDate','cash_payment_date'),('dividStockMarketDate','stock_listing_date')]:assert row[field]==d[name]
 component={MIXED:{'verified':True,'kind':'PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION','source_file':d['file'],'source_sha256':d['sha256'],'source_row_sha256':digest(row),'record_date':d['record_date'],'ex_date':d['ex_date'],'cash_payment_date':d['cash_payment_date'],'stock_listing_date':d['stock_listing_date'],'primary_pages':d['primary_pages'],'components':comps,'source_scalar_rounding_algorithm_certified':False,'fractional_registry_allocation_certified':False}}
 row=vendor('SZ000975|2026-04-24');p=precision['SZ000975|2026-04-24'];assert p['source_row_sha256']==digest(row) and Decimal(p['expected_vendor_cash_per_share'])==Decimal(row['dividCashPsBeforeTax']);eff=Decimal(p['effective_cash_per_share']);raw=Decimal(row['dividCashPsBeforeTax']);assert eff>raw and eff.quantize(Decimal(1).scaleb(raw.as_tuple().exponent),rounding=ROUND_DOWN)==raw
 needed=[]
 def use(p):
  if p.get('source_file'):
   doc=documents[p['source_file']];assert doc['sha256']==p['source_sha256']
   if doc['file'] not in needed:needed.append(doc['file'])
  for part in ['implementation','supplement']:
   if p.get(part):use(p[part])
 for p in [*supplements,*capital.values(),*unknown.values(),*precision.values(),*component.values()]:use(p)
 assert len(needed)==17
 return {'documents':[documents[n] for n in needed],'capital_tax':capital,'unresolved_tax':unknown,'stock_dividend_tax_bases':{},'supplementary_distributions':supplements,'cash_override_contract':'PRIMARY_NOTICE_CASH_PRECISION_V1','cash_overrides':precision,'component_precision_contract':'PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION_V1','component_precision_overrides':component,'cached_literal_proof_origins':{'supplements':co,'capital':ca,'unresolved':un,'cash_precision':po}}

def verify_semantics(actual,expected):
 for key,val in expected.items():assert actual[key]==val,key
 assert actual['direct_primary_capital_tax_statements']==3 and actual['conditional_capital_tax_inferences']==2
 for key in ['strict_statutory_capital_tax_certification','fractional_registry_allocation_certified','source_scalar_rounding_algorithm_certified','events_compiled','event_compilation_admitted','admitted_for_account_replay','full_corporate_action_completeness_certified','historical_arrival_verified','actual_FIFO_tax_liability_verified','portfolio_returns_computed','objective_achieved']:assert actual[key] is False,key
 assert actual['new_source_queries']==0 and actual['component_precision_proof_is_metadata_only'] is True and actual['old2024_SH603596_tax_guard_unchanged'] is True

def negative(fn):
 try:fn()
 except (AssertionError,ValueError,KeyError):return True
 raise AssertionError('negative accepted')

def main():
 planpath=R/'experiments/qlib/price-delay-horizon-proof-projection-request.json';assert sha(planpath)==REQ
 assert hashlib.sha256(subprocess.check_output(['git','show','1d3db1b:experiments/qlib/price-delay-horizon-proof-projection-request.json'],cwd=R)).hexdigest()==REQ
 plan=read(planpath);assert sha(O/'reviewed-manifest.json')==MAN and sha(O/'summary.json')==SUMMARY;m=read(O/'reviewed-manifest.json');s=read(O/'summary.json')
 for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B),('primary_files_sha256',B),('immutable_financial_sha256',B)]:
  for n,h in plan[field].items():assert sha(safe(root,n))==h
 for root,expected in plan['immutable_trees_sha256'].items():assert {str(p.relative_to(B/root)):sha(p) for p in (B/root).rglob('*') if p.is_file()}==expected
 oldaudit=read(B/'price-delay-event-source-independent-audit-20261021.json');assert sha(B/'price-delay-event-source-independent-audit-20261021.json')=='934b8a825b3d4662f7bd8f54fb87c6136801a71aee4efd99db7a9ae74af7d201'
 oe=B/'price-delay-account-source-events-20261021';op=B/'price-delay-corporate-reviewed-20261021';os=read(oe/'summary.json')
 assert oldaudit['summary_sha256']==sha(oe/'summary.json') and oldaudit['reviewed_manifest_sha256']==sha(op/'reviewed-manifest.json') and oldaudit['raw_manifest_sha256']==sha(B/'price-delay-raw-dev-20261021/manifest.json')
 for n,h in os['artifact_sha256'].items():assert sha(oe/n)==h
 events,receipts=read(oe/'derived_events.json'),read(oe/'event_source_receipts.json');assert len(events)==len(receipts)==378
 assert all(e['event_id']==r['event_id'] for e,r in zip(events,receipts))
 unknown=[r for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']];assert len(unknown)==1 and unknown[0]['instrument']=='SH603596' and unknown[0]['ex_date']=='2024-05-20'
 docs=read(oe/'effective_proofs.json')['documents'];assert len(docs)==15
 for d in docs:assert sha(op/d['file'])==d['sha256']
 rawroot=B/'price-delay-raw-horizon-v2-20261021';rawm=read(rawroot/'manifest.json');calendar=read(rawroot/'calendar.json')['sessions'];oldraw=B/'price-delay-raw-dev-20261021';oldm=read(oldraw/'manifest.json');oldcal=read(oldraw/'calendar.json')['sessions']
 assert len(calendar)==676 and len(oldcal)==486 and calendar[:486]==oldcal and len(rawm['per_code_sha256'])==203 and len(oldm['per_code_sha256'])==151
 assert sha(rawroot/'calendar.json')==rawm['calendar_sha256'] and sha(oldraw/'calendar.json')==oldm['calendar_sha256']
 for code,rawsha in rawm['per_code_sha256'].items():
  path=rawroot/'codes'/(code+'.json');assert sha(path)==rawsha;packet=read(path);assert [r['date'] for r in packet['bars']]==calendar
  if code in oldm['per_code_sha256']:
   oldpath=oldraw/'codes'/(code+'.json');assert sha(oldpath)==oldm['per_code_sha256'][code];oldpacket=read(oldpath)
   for field,datefield in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:assert [r for r in packet[field] if r[datefield]<'2026-01-01']==oldpacket[field]
 chains=primary_chains(plan);assert m['source_evidence_chains']==chains
 expected=expected_proofs(plan,chains);verify_semantics(m,expected)
 assert set(s['artifact_sha256'])=={x['file'] for x in m['documents']}|{'reviewed-manifest.json'}
 for n,h in s['artifact_sha256'].items():assert sha(O/n)==h
 assert {p.name for p in O.iterdir()}==set(s['artifact_sha256'])|{'summary.json'}
 for d in m['documents']:
  assert (O/d['file']).read_bytes()==safe(B,plan['primary_evidence'][d['file']]['pdf_file']).read_bytes()
  chain=d['source_evidence_chain'];assert chain==chains[d['file']] and d['day']==d.get('publication_day',d['day'])
  if chain['chain_kind']=='AUTHENTICATED_REVIEWED_BYTE_REUSE_ONLY':assert not d.get('pdf_receipt')
 assert s['projection_request_sha256']==m['projection_request_sha256']==REQ and s['reviewed_manifest_sha256']==MAN
 assert s['primary_HTTP_chains']==14 and s['primary_reviewed_byte_reuse_only']==3 and s['capital_supported']==5 and s['supplementary_distributions']==8 and s['unresolved_tax_keys']==['SH603606|2026-05-26','SZ000937|2026-06-17']
 for f in ['source_admitted_for_account_replay','portfolio_returns_computed','full_October_complete','objective_achieved','events_compiled','account_replay_run']:assert s[f] is False
 for f in ['original378_source_and15PDF_and48_financial_artifacts_unchanged','original_failed_capture_unchanged','input_maps_rechecked_after_projection']:assert s[f] is True
 assert s['copied_original_PDFs']==17 and s['source_queries']==0
 negatives={}
 for label,change in [
 ('reference_cash_replaces_actual',lambda x:x['supplementary_distributions'][-1]['record'].__setitem__('dividCashPsBeforeTax','1.17')),
 ('cached_cash_literal_changed',lambda x:x['supplementary_distributions'][0]['record'].__setitem__('dividCashPsBeforeTax','999')),
 ('conditional_upgraded_direct',lambda x:x['capital_tax'][MIXED].__setitem__('evidence_kind','DIRECT_ISSUER_NO_TAX')),
 ('unknown606_exempt',lambda x:x['unresolved_tax']['SH603606|2026-05-26'].__setitem__('verified_exempt',True)),
 ('unknown937_modified',lambda x:x['unresolved_tax']['SZ000937|2026-06-17'].__setitem__('strict_tax_admission_resolved',True)),
 ('975_precision_changed',lambda x:x['cash_overrides']['SZ000975|2026-04-24'].__setitem__('effective_cash_per_share','999')),
 ('2831_rounded_vendor_as_primary',lambda x:x['component_precision_overrides'][MIXED]['components']['cash_per_share'].__setitem__('effective_per_share','0.803813')),
 ('2831_fractional_allocation_certified',lambda x:x.__setitem__('fractional_registry_allocation_certified',True)),
 ('source_admission_promoted',lambda x:x.__setitem__('admitted_for_account_replay',True)),
 ('byte_reuse_promoted_HTTP',lambda x:next(d for d in x['documents'] if d['file']=='SH601128-20260603.pdf')['source_evidence_chain'].__setitem__('HTTP_decoded_body_matches_PDF',True)),
 ('wrong_ex_date',lambda x:x['supplementary_distributions'][-1]['record'].__setitem__('dividOperateDate','2026-10-19'))]:
  wrong=copy.deepcopy(m);change(wrong);negatives[label]=negative(lambda:verify_semantics(wrong,expected))
 result={'status':'INDEPENDENT_SOURCE_PROOF_PROJECTION_OUTPUT_RECONSTRUCTED_NOT_EVENTS_OR_ACCOUNT','audit_code_sha256':sha(Path(__file__)),'imports_project_code':False,'production_project_sources_called':False,'projection_request_sha256':REQ,'freeze_commit_request_bytes_verified':'1d3db1b','reviewed_manifest_sha256':MAN,'summary_sha256':SUMMARY,'all17_PDFs_byte_exact':True,'all_projected_proof_objects_independently_reconstructed':True,'all17_projected_document_metadata_objects_reconstructed':True,'all14_original_HTTP_chains_reconstructed':True,'three_original_reviewed_byte_reuse_routes_keep_missing_HTTP_limits':True,'all18_output_artifact_hashes_verified':True,'original378_event_receipt_objects_and_files_unchanged':True,'original15_PDF_bytes_unchanged':True,'all48_financial_bytes_unchanged':True,'all5_immutable_input_trees_unchanged':True,'all203_source_packet_hashes_and676_sessions_reverified':True,'all151_literal_pre2026_raw_prefixes_and486_calendar_reverified':True,'six_cached_cash_supplements_literal':True,'three_cached_capital_proofs_literal':True,'old975cash_precision_literal':True,'old937unknown_literal':True,'new_cash_supplements':2,'capital_proof_counts':{'total':5,'direct':3,'conditional':2},'unknown_keys':['SH603606|2026-05-26','SZ000937|2026-06-17'],'2831_component_precision_metadata_reconstructed_from_original_row_and_primary_per10':True,'semantic_negative_controls_rejected':negatives,'critical_or_important_findings':[],'critical':[],'important':[],'limits':['Independent stdlib reconstruction consumes frozen source packets/cache proofs/reviews and checks full projected proof/document objects; no production projector, event compiler or account imported/called.','Metadata-level verified_exempt is event-specific direct/conditional evidence classification, not statutory/FIFO tax certification or a completed account guard.','No new PDF-content rereview: the original paired full-page content reviews and older authenticated content references are preserved and bound.','Three byte-reuse routes remain without original HTTP body evidence; fourteen other chains have full saved request/reservation/decoded-body correspondence.','Original2024 unknown, current937/606 unknown and2831 fractional registry limitations remain. No guard is waived.','No network, new source queries, event compilation, account run or portfolio ROI; source/account admission remains false.'],'source_admitted_for_account_replay':False,'events_compiled':False,'portfolio_returns_computed':False,'objective_achieved':False}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(OUT);print(sha(OUT));print('semantic negatives',len(negatives))
if __name__=='__main__':main()
