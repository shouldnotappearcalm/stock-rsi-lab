"""Frozen primary-evidence projection only; no account/event compilation.

Real source use requires the separately frozen preparation adapter.
Only stdlib. Source authentication and pure metadata projection are separate.
"""
import base64
import copy
import hashlib
import json
import re
from decimal import Decimal as D,ROUND_DOWN
from fractions import Fraction
from pathlib import Path

OUTPUT='price-delay-horizon-corporate-reviewed-20261021'
CONTRACT='PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION_V1'
KIND='PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION'
CASH_CONTRACT='PRIMARY_NOTICE_CASH_PRECISION_V1'
CASH_KEYS=('SH601598|2026-10-20','SH601918|2026-02-06','SH601966|2026-06-24','SZ002608|2026-10-19','SZ002756|2026-10-20','SZ002812|2026-10-20')
CAPITAL_KEYS={'SH601128|2026-06-09','SH603737|2026-06-01','SZ002595|2026-05-11'}
UNRESOLVED='SZ000937|2026-06-17'
MIXED='SZ002831|2026-06-04'
NOTICE_KEYS={'SH603233','SH603605','SH603596','SH603606','SZ002831'}


def need(ok,message):
 if not ok:raise ValueError(message)


def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def file_sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())

def path_under(root,name):
 p=Path(name);root=Path(root).resolve()
 need(not p.is_absolute() and '..' not in p.parts,'safe source-relative path required')
 out=(root/p).resolve();need(out.is_relative_to(root),'source symlink escapes authenticated root');return out


def authenticate_file_map(root,bindings):
 need(isinstance(bindings,dict),'file bindings must be a map');result={}
 for name,sha in bindings.items():
  need(isinstance(sha,str) and re.fullmatch('[0-9a-f]{64}',sha) is not None,'canonical file SHA required')
  p=path_under(root,name);need(file_sha(p)==sha,'authenticated source changed: '+name);result[str(p)]=sha
 return result


def check_http_chain(identity,reservation,response,pdf,expected_identity,reservation_sha,max_bytes=10485760):
 need(identity==expected_identity and identity.get('source')=='CNINFO_HTTP' and isinstance(identity.get('url'),str),'original registered HTTP identity required')
 key=digest(identity)
 need(reservation['identity_sha256']==key and type(reservation['attempt']) is int and reservation['attempt']==1,'single original reservation required')
 need(response['identity_sha256']==key and response['reservation_sha256']==reservation_sha and response['status']=='CAPTURED','response/reservation link changed')
 payload=response['payload'];need(response['payload_sha256']==digest(payload) and payload['fields']==['http_response'] and len(payload['rows'])==1,'one bound decoded HTTP response required')
 r=payload['rows'][0]
 need(type(r['status']) is int and r['status']==200 and r['final_url']==identity['url'] and r['body_complete'] is True and r['body_truncated'] is False and r['read_error_type'] is None and r['read_error'] is None,'original complete no-redirect HTTP body required')
 raw=base64.b64decode(r['body_base64'],validate=True)
 need(raw==pdf and raw.startswith(b'%PDF') and len(raw)<=max_bytes,'original HTTP body differs from authenticated PDF')
 return {'HTTP_decoded_body_matches_PDF':True,'HTTP_wire_transport_certified':False,'historical_arrival_certified':False}


def amount(text):
 need(isinstance(text,str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',text) is not None,'plain decimal source amount required')
 x=D(text);need(x.is_finite() and x>=0,'nonnegative finite source amount required');return x


def source_key(code,row):return code+'|'+row['dividOperateDate']


def collect_cached(cached,field,keys):
 result={};origins={}
 for origin,p in cached.items():
  local={}
  if field=='supplementary_distributions':
   for item in p.get(field,[]):
    key=source_key(item['instrument'],item['record'])
    need(key not in local,'duplicate primary supplement inside one source origin');local[key]=item
  else:local=p.get(field,{})
  for key,value in local.items():
   if key not in keys:continue
   need(key not in result or result[key]==value,'conflicting cached primary interpretations')
   result[key]=copy.deepcopy(value);origins.setdefault(key,[]).append(origin)
 need(set(result)==set(keys),'missing required cached source interpretation')
 return result,origins


def row_for(packets,key):
 code,ex=key.split('|');rows=[r for r in packets[code]['distributions'] if r['dividOperateDate']==ex]
 need(len(rows)==1,'unique original vendor distribution required: '+key);return rows[0]


def notice_dates_match(row,d):
 fields={'dividPlanDate':'publication_day','dividRegistDate':'record_date','dividOperateDate':'ex_date','dividPayDate':'cash_payment_date','dividStockMarketDate':'stock_listing_date'}
 need(all(row.get(r,'')==(d.get(n) or '') for r,n in fields.items()),'original vendor and primary economic/publication dates disagree')
 need(d['publication_day']<d['record_date']<d['ex_date'] and d['cash_payment_date']>=d['ex_date'],'invalid primary economic timing')


def bind(proof,key,documents):
 d=documents[proof['source_file']];code,ex=key.split('|')
 need(d['instrument']==code and d['sha256']==proof['source_sha256'],'source proof/document identity mismatch')
 need(d.get('day',d.get('publication_day'))<ex,'primary document after economic event')
 return d


def _tax_notice(d,kind):
 need(d['direct_premium_source_and_no_tax_statement'] is (kind=='DIRECT'),'source tax evidence level upgraded')
 if kind=='CONDITIONAL':need(d['capital_tax_evidence_level']=='PREMIUM_BALANCE_AND_EXPLICIT_CASH_TAX_AMOUNT_CONDITIONAL_INFERENCE','conditional inference evidence classification changed')
 if kind=='UNRESOLVED':need(d['capital_tax_evidence_level']=='UNRESOLVED_GENERAL_CAPITAL_RESERVE_ONLY','unresolved general reserve evidence changed')


def make_cash_supplement(packets,d):
 code=d['instrument'];key=code+'|'+d['ex_date']
 need(not any(r['dividOperateDate']==d['ex_date'] for r in packets[code]['distributions']),'primary supplement would duplicate vendor entitlement')
 need(amount(d['stock_per_original_share'])==amount(d['capital_per_original_share'])==0 and d.get('stock_listing_date') is None,'cash-only primary notice required')
 expected={'SH603233':'0.41','SH603605':'1.18'}[code]
 need(amount(d['cash_per_original_share_CNY'])==D(expected),'actual eligible-holder cash differs from reviewed primary amount')
 need(d['publication_day']<d['record_date']<d['ex_date']<=d['cash_payment_date'],'primary record/ex/pay timing changed')
 record={'code':code[:2].lower()+'.'+code[2:],'dividPlanDate':d['publication_day'],'dividRegistDate':d['record_date'],
  'dividOperateDate':d['ex_date'],'dividPayDate':d['cash_payment_date'],'dividStockMarketDate':'',
  'dividCashPsBeforeTax':d['cash_per_original_share_CNY'],'dividStocksPs':'0','dividReserveToStockPs':'0','dividCashStock':'PRIMARY_CASH_ONLY_NOTICE'}
 return {'instrument':code,'record':record,'source_file':d['file'],'source_sha256':d['sha256'],'primary_pages':copy.deepcopy(d['primary_pages']),
  'record_origin':'Separately authenticated issuer implementation notice, not a vendor rewrite or factor-derived payment',
  'reference_price_cash_per_share_not_entitlement':d.get('price_reference_cash_per_share_CNY')}


def mixed_precision(row,d):
 need(d['instrument']=='SZ002831' and d['ex_date']=='2026-06-04','single mixed precision event scope required');notice_dates_match(row,d)
 need(amount(row['dividStocksPs'])==amount(d['stock_per_original_share'])==0,'mixed precision cannot alter stock dividend')
 comps={}
 for attr,rawfield,per10field,expected in [('cash_per_share','dividCashPsBeforeTax','cash_per_10_original_shares_CNY','0.8038127'),
   ('capital_per_share','dividReserveToStockPs','capital_per_10_original_shares','0.4019063')]:
  raw=row[rawfield];effective=d['cash_per_original_share_CNY' if attr=='cash_per_share' else 'capital_per_original_share'];per10=d[per10field]
  need(re.fullmatch(r'[0-9]+\.[0-9]{6}',raw) is not None,'six published decimal original scalar required')
  need(effective==expected and Fraction(amount(effective))==Fraction(amount(per10))/10 and
    Fraction(amount(raw))!=Fraction(amount(effective)) and abs(Fraction(amount(raw))-Fraction(amount(effective)))<=Fraction(1,2000000),'actual final primary per10/per-share precision must be source consistent, not reference/proposal')
  comps[attr]={'expected_vendor_per_share':raw,'primary_per10_original_shares':per10,'effective_per_share':effective}
 return {'verified':True,'kind':KIND,'source_file':d['file'],'source_sha256':d['sha256'],'source_row_sha256':digest(row),
  'record_date':d['record_date'],'ex_date':d['ex_date'],'cash_payment_date':d['cash_payment_date'],'stock_listing_date':d['stock_listing_date'],
  'primary_pages':copy.deepcopy(d['primary_pages']),'components':comps,
  'source_scalar_rounding_algorithm_certified':False,'fractional_registry_allocation_certified':False}


def project_sources(bundle):
 """Pure projection only; requires caller's authenticated filesystem bundle.

 Its returned metadata is not an event list, source admission or account result.
 """
 before=digest({k:v for k,v in bundle.items() if k!='PDF_bytes'})
 packets=bundle['packets'];cached=bundle['cached'];notices=canonical_reviewed_notices(bundle['reviews']);documents=bundle['documents']
 need(set(notices)==NOTICE_KEYS,'exact five independently reviewed new notices required')
 need(len(bundle['old_events'])==len(bundle['old_receipts'])==378,'original paired378 source artifacts required')
 old=[e for e in bundle['old_events'] if e.get('instrument')=='SH603596' and e.get('ex_date')=='2024-05-20']
 need(len(old)==1 and old[0]['capital_tax_exempt_verified'] is False,'2026 primary must never upgrade original2024 unknown tax event')
 guards=[r for r in bundle['old_receipts'] if r.get('requires_zero_record_ownership_if_tax_unverified')]
 need(len(guards)==1 and guards[0]['instrument']=='SH603596' and guards[0]['ex_date']=='2024-05-20','old pre2026 zero ownership guard changed')
 cash,origins=collect_cached(cached,'supplementary_distributions',CASH_KEYS)
 capital,capital_origins=collect_cached(cached,'capital_tax',CAPITAL_KEYS)
 unresolved,unresolved_origins=collect_cached(cached,'unresolved_tax',{UNRESOLVED})
 precision,precision_origins=collect_cached(cached,'cash_overrides',{'SZ000975|2026-04-24'})
 for key,p in cash.items():
  d=bind(p,key,documents);code,ex=key.split('|');need(not any(r['dividOperateDate']==ex for r in packets[code]['distributions']),'cached supplement duplicates vendor event')
  need(p['record']['dividPlanDate']==d.get('day',d.get('publication_day')) and amount(p['record']['dividStocksPs'])==amount(p['record']['dividReserveToStockPs'])==0,'cached cash proof issuer/day/components changed')
 for key,p in capital.items():
  bind(p,key,documents);r=row_for(packets,key);need(p['verified_exempt'] is True and amount(r['dividReserveToStockPs'])>0,'inherited capital proof must remain applicable')
  if key=='SZ002595|2026-05-11':need(p.get('evidence_kind')=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE','inherited conditional capital evidence upgraded')
 need(unresolved[UNRESOLVED].get('verified_exempt') is False and unresolved[UNRESOLVED].get('strict_tax_admission_resolved') is False,'literal unknown937 cannot become exempt')
 p=precision['SZ000975|2026-04-24'];r=row_for(packets,'SZ000975|2026-04-24');bind(p,'SZ000975|2026-04-24',documents)
 need(p['verified'] is True and p['kind']=='PRIMARY_NOTICE_CASH_PRECISION' and p['source_row_sha256']==digest(r) and
  amount(r['dividCashPsBeforeTax'])==amount(p['expected_vendor_cash_per_share']) and amount(r['dividStocksPs'])==0 and amount(r['dividReserveToStockPs'] or '0')==0 and not r['dividStockMarketDate'],'old cash precision proof must bind exact original cash-only row')
 raw=amount(r['dividCashPsBeforeTax']);eff=amount(p['effective_cash_per_share'])
 need(eff>raw and eff.quantize(D(1).scaleb(raw.as_tuple().exponent),rounding=ROUND_DOWN)==raw,'old cash precision contract cannot become an arbitrary correction')
 for code,kind in [('SH603596','DIRECT'),('SH603606','UNRESOLVED'),('SZ002831','CONDITIONAL')]:
  d=notices[code];_tax_notice(d,kind);r=row_for(packets,code+'|'+d['ex_date']);notice_dates_match(r,d)
  if code!='SZ002831':need(amount(r['dividCashPsBeforeTax'])==amount(d['cash_per_original_share_CNY']) and amount(r['dividReserveToStockPs'])==amount(d['capital_per_original_share']),'primary and unchanged vendor scalar economics differ')
 d=notices['SH603596'];capital['SH603596|2026-05-11']={'verified_exempt':True,'source_file':d['file'],'source_sha256':d['sha256'],
  'pages_one_based':copy.deepcopy(d.get('field_pages',{}).get('premium_source_and_transfer_no_tax',[3])),
  'evidence_kind':'DIRECT_ISSUER_PREMIUM_SOURCE_AND_TRANSFER_NO_TAX_STATEMENT','strict_statutory_capital_tax_certification':False,
  'evidence':'Original issuer notice explicitly identifies share-premium source and this event transfer no-tax; this2026 event only, not2024.'}
 d=notices['SZ002831'];capital[MIXED]={'verified_exempt':True,'source_file':d['file'],'source_sha256':d['sha256'],'pages_one_based':[2,3],
  'evidence_kind':'PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE','strict_statutory_capital_tax_certification':False,
  'issuer_explicit_transfer_no_tax_statement':False,'evidence':'Conditional inference from premium-balance ceiling and separately published rounded cash-only tax examples; no exclusive premium tracing or statutory certificate.',
  'tax_examples':{'cash_per_ten':'8.038127','one_month_tax_per_ten':'1.607625','one_year_tax_per_ten':'0.803813','printed_examples_rounded':True}}
 d=notices['SH603606'];unresolved['SH603606|2026-05-26']={'verified_exempt':False,'strict_tax_admission_resolved':False,
  'issuer_explicit_no_tax_statement':False,'implementation':{'source_file':d['file'],'source_sha256':d['sha256'],'primary_pages':copy.deepcopy(d['primary_pages']),
   'cash_per_original_share':d['cash_per_original_share_CNY'],'capital_per_original_share':d['capital_per_original_share'],'record_day':d['record_date'],'ex_pay_list_day':d['ex_date']},
  'evidence_assessment':'All original notice pages show generic reserve only; no premium source/no-tax statement. Cash-tax examples alone do not resolve capital tax.',
  'account_behavior_required':'Fail before mutation at exdate for any positive recorded inventory; zero record ownership only, never alter targets to bypass.'}
 supplements=[cash[k] for k in CASH_KEYS]+[make_cash_supplement(packets,notices[c]) for c in ('SH603233','SH603605')]
 component={MIXED:mixed_precision(row_for(packets,MIXED),notices['SZ002831'])}
 # Only consumed original documents. Retain actual original metadata, including missing HTTP receipt limits.
 needed={}
 def consume(proof):
  if proof.get('source_file'):
   d=documents[proof['source_file']];need(d['sha256']==proof['source_sha256'],'consumed original PDF hash mismatch');needed[d['file']]=copy.deepcopy(d);needed[d['file']]['day']=d.get('day',d.get('publication_day'))
   need(needed[d['file']]['day']==d.get('publication_day',needed[d['file']]['day']),'canonical document day must retain conservative publication date')
  for part in ('implementation','supplement'):
   if proof.get(part):consume(proof[part])
 for proof in [*supplements,*capital.values(),*unresolved.values(),*precision.values(),*component.values()]:consume(proof)
 need(len(needed)==17,'exact seventeen distinct consumed2026 primary PDFs required')
 result={'status':'PRICE_DELAY_2026_REVIEWED_SOURCE_PROJECTION_EVENTS_AND_ACCOUNT_PENDING','documents':list(needed.values()),
  'capital_tax':capital,'unresolved_tax':unresolved,'stock_dividend_tax_bases':{},'supplementary_distributions':supplements,
  'cash_override_contract':CASH_CONTRACT,'cash_overrides':precision,'component_precision_contract':CONTRACT,'component_precision_overrides':component,
  'cached_literal_proof_origins':{'supplements':origins,'capital':capital_origins,'unresolved':unresolved_origins,'cash_precision':precision_origins},
  'direct_primary_capital_tax_statements':3,'conditional_capital_tax_inferences':2,'strict_statutory_capital_tax_certification':False,
  'old2024_SH603596_tax_guard_unchanged':True,'original378_event_and_receipt_files_must_remain_byte_exact':True,
  'fractional_registry_allocation_certified':False,'source_scalar_rounding_algorithm_certified':False,
  'component_precision_proof_is_metadata_only':True,'events_compiled':False,'event_compilation_admitted':False,
  'admitted_for_account_replay':False,'full_corporate_action_completeness_certified':False,'historical_arrival_verified':False,
  'actual_FIFO_tax_liability_verified':False,'portfolio_returns_computed':False,'new_source_queries':0,'objective_achieved':False}
 validate_projection(result)
 need(before==digest({k:v for k,v in bundle.items() if k!='PDF_bytes'}),'projection mutated original inputs')
 return result


def _document_matches(value,expected):
 """Find an original document identity inside an authenticated manifest/review."""
 if isinstance(value,dict):
  # Legacy reviewed documents use a named PDF SHA map or a single PDF plus issuer.
  pdf_map=value.get('pdf_sha256')
  if isinstance(pdf_map,dict) and pdf_map.get(Path(expected['file']).stem)==expected['sha256']:
   return True
  if pdf_map==expected['sha256'] and value.get('sourcefacts',{}).get('instrument')==expected['instrument']:
   return True
  if value.get('sha256')==expected['sha256'] and isinstance(value.get('file'),str) and Path(value['file']).name==expected['file']:
   return value.get('instrument',expected['instrument'])==expected['instrument']
  return any(_document_matches(x,expected) for x in value.values())
 if isinstance(value,list):return any(_document_matches(x,expected) for x in value)
 return False


def authenticate_primary_evidence(base,repo,spec,base_bindings,repo_bindings):
 """Validate registered original file/review/receipt chains without source calls.

 All maps and spec must themselves be bound by the caller's external frozen plan.
 This function does NOT make a captured PDF into new economic or tax evidence.
 """
 roots={'base':Path(base),'repo':Path(repo)};maps={'base':base_bindings,'repo':repo_bindings};bound={}
 def verified(kind,name):
  need(name in maps[kind],'primary chain file absent from frozen bindings: '+name)
  path=path_under(roots[kind],name);need(file_sha(path)==maps[kind][name],'primary chain original bytes changed: '+name)
  bound[str(path)]=maps[kind][name];return path
 pdf_path=verified('base',spec['pdf_file']);pdf=pdf_path.read_bytes()
 need(file_sha(pdf_path)==spec['pdf_sha256'] and pdf.startswith(b'%PDF'),'original registered PDF required')
 manifest=read(verified('base',spec['source_manifest_file']));values=manifest['documents'];values=list(values.values()) if isinstance(values,dict) else values
 matches=[d for d in values if d.get('file')==spec['source_document_file'] and d.get('sha256')==spec['pdf_sha256']]
 need(len(matches)==1,'one original manifest document must bind PDF bytes');document=copy.deepcopy(matches[0])
 need(bool(spec.get('content_review_refs')),'authenticated content-review reference required, PDF presence alone insufficient')
 for ref in spec['content_review_refs']:
  need(ref['root'] in roots,'registered review root required');review=read(verified(ref['root'],ref['file']))
  need(_document_matches(review,document),'content review does not bind same issuer/PDF identity')
 route=spec['route']
 if route=='HTTP':
  receipt=document.get('pdf_receipt');need(isinstance(receipt,dict),'original document HTTP receipt required')
  cap=spec['capture_root'];chain={}
  for kind in ('request','reserved','response'):
   name=str(Path(cap)/receipt[kind+'_file']);path=verified('base',name)
   need(file_sha(path)==receipt[kind+'_sha256'],'original manifest receipt SHA changed');chain[kind]=read(path)
  need(spec['expected_identity'].get('url')==document['url'],'registered expected identity URL must match original document')
  details=check_http_chain(chain['request'],chain['reserved'],chain['response'],pdf,spec['expected_identity'],receipt['reserved_sha256'])
  chain_kind='ORIGINAL_REQUEST_RESERVATION_DECODED_HTTP_BODY_PDF'
 elif route=='REVIEWED_BYTE_REUSE':
  # Existing receipt nulls remain null. The caller binds prior reviewed/capture
  # provenance rather than relabelling this copy as a fresh HTTP observation.
  need('expected_identity' not in spec and 'capture_root' not in spec,'byte reuse must not manufacture a new HTTP request')
  details={'HTTP_decoded_body_matches_PDF':False,'HTTP_wire_transport_certified':False,'historical_arrival_certified':False}
  chain_kind='AUTHENTICATED_REVIEWED_BYTE_REUSE_ONLY'
 else:raise ValueError('unsupported primary evidence source route')
 for path,expected in bound.items():need(file_sha(path)==expected,'primary chain changed while being authenticated')
 return {'document':document,'source_PDF_file':str(pdf_path),'source_PDF_sha256':spec['pdf_sha256'],
  'chain_kind':chain_kind,**details,'authenticated_original_files':bound,'new_source_query':False,'financial_admission':False}


def write_projection(output,proposal,pdf_sources):
 """Exclusive copy to a NEW destination; not called on real data by this draft.

 Caller must freeze the plan/code, authenticate all input maps, build via the pure
 projection, recheck all48 financial hashes and old source trees before and after.
 """
 output=Path(output)
 validate_projection(proposal)
 need(output.name==OUTPUT and not output.exists(),'new fixed reviewed-projection output required')
 need(proposal['status']=='PRICE_DELAY_2026_REVIEWED_SOURCE_PROJECTION_EVENTS_AND_ACCOUNT_PENDING' and
  proposal['events_compiled'] is False and proposal['event_compilation_admitted'] is False and
  proposal['admitted_for_account_replay'] is False and proposal['portfolio_returns_computed'] is False,'projection must remain source metadata only')
 docs=proposal['documents'];need(len(docs)==17 and len({d['file'] for d in docs})==17,'seventeen unique consumed original PDFs required')
 need(set(pdf_sources)=={d['file'] for d in docs},'PDF copy bindings must match consumed source documents exactly')
 blobs={}
 for d in docs:
  name=d['file'];need(Path(name).name==name,'safe primary copy filename required')
  blob=Path(pdf_sources[name]).read_bytes();need(blob.startswith(b'%PDF') and hashlib.sha256(blob).hexdigest()==d['sha256'],'original primary changed before copy')
  blobs[name]=blob
 # Validate everything above before creating any real output directory.
 encoded=(json.dumps(proposal,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode()
 output.mkdir(parents=False,exist_ok=False)
 for name,blob in blobs.items():
  with (output/name).open('xb') as f:f.write(blob)
 with (output/'reviewed-manifest.json').open('xb') as f:f.write(encoded)
 need(all(file_sha(output/d['file'])==d['sha256'] for d in docs),'copied PDF byte verification failed')
 return {'reviewed_manifest_sha256':file_sha(output/'reviewed-manifest.json'),'copied_original_PDFs':17,
  'source_queries':0,'events_compiled':False,'account_replay_run':False,'portfolio_returns_computed':False}


REVIEW_FILES={
 'four_root':('experiments/qlib/price-delay-horizon-four-primary-content-review.json','8405862ab4ba8c2c44744a3ec2850dfaec808608b12c418761ec5cb232af3358'),
 'four_independent':('experiments/qlib/price-delay-horizon-four-primary-independent-review.json','04a8799f185d307df892f9b8182a7c8969f4bc0e46520d06d3aaf4644dcc2701'),
 'single_root':('experiments/qlib/price-delay-horizon-single-primary-content-review.json','b20a662cc6149c96397089a769f3e43dd96b85039c13ea544441cb4a17c6285f'),
 'single_independent':('experiments/qlib/price-delay-horizon-single-primary-independent-review.json','32a97c9f083df960b7b0b111bac72b66c198f684ba96018c8ea0d50b5fe8d97e')}


def load_reviewed_notices(repo):
 """Fixed SHA reader, permitted only within the later frozen-plan adapter.

 Never accepts caller-provided strength labels or alternative review files.
 Returns the raw paired schemas, not a projected reviewed manifest.
 """
 bindings={file:sha for file,sha in REVIEW_FILES.values()};snapshots=authenticate_file_map(repo,bindings)
 reviews={kind:read(path_under(repo,file)) for kind,(file,_) in REVIEW_FILES.items()}
 reviews['binding_sha256']={kind:sha for kind,(_,sha) in REVIEW_FILES.items()}
 for path,sha in snapshots.items():need(file_sha(path)==sha,'review source changed while authenticated')
 return reviews


def canonical_reviewed_notices(reviews):
 """Map authenticated paired schemas explicitly; no caller strength normalization.

 Pure counterpart supports synthetic tests. Real callers MUST obtain `reviews`
 from load_reviewed_notices inside a separately frozen/hash-authenticated adapter.
 """
 refs=reviews['binding_sha256'];root=reviews['four_root'];ind=reviews['four_independent']
 need(ind['root_content_review_sha256']==refs['four_root'] and ind['critical']==[] and ind['important']==[] and
  ind['all18_pages_independently_text_extracted_and_visually_reviewed'] is True,'four-notice independent/root review binding required')
 rootdocs={d['instrument']:d for d in root['documents']};inddocs={d['instrument']:d for d in ind['documents']}
 codes={'SH603605','SH603596','SH603606','SZ002831'}
 need(set(rootdocs)==set(inddocs)==codes and len(root['documents'])==len(ind['documents'])==4,'four exact original notice identities required')
 tax={
 'SH603605':('NOT_APPLICABLE_CASH_ONLY','NOT_APPLICABLE_NO_NONCASH',False),
 'SH603596':('DIRECT_PREMIUM_SOURCE_AND_NO_TAX_STATEMENT','DIRECT_ISSUER_PREMIUM_SOURCE_AND_TRANSFER_NO_TAX_STATEMENT',True),
 'SH603606':('UNRESOLVED_NO_PREMIUM_SOURCE_OR_NO_TAX_STATEMENT_IN_ALL5PAGES','UNRESOLVED_GENERAL_CAPITAL_RESERVE_ONLY',False),
 'SZ002831':('PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE_CANDIDATE_NOT_DIRECT','PREMIUM_BALANCE_AND_EXPLICIT_CASH_TAX_AMOUNT_CONDITIONAL_INFERENCE',False)}
 fields=('instrument','file','sha256','publication_day','record_date','ex_date','cash_payment_date','stock_listing_date',
  'cash_per_original_share_CNY','capital_per_original_share','stock_per_original_share')
 result={}
 for code in sorted(codes):
  a,b=rootdocs[code],inddocs[code]
  need(all(a.get(k)==b.get(k) for k in fields),'root/independent notice economic, identity or date literal mismatch: '+code)
  rk,ik,direct=tax[code]
  need(a['capital_tax_evidence_kind']==rk and b['capital_tax_evidence_level']==ik and
   b['direct_premium_source_and_no_tax_statement'] is direct,'unapproved source evidence classification change: '+code)
  mapping={'root_tax_field':'capital_tax_evidence_kind','root_tax_literal':rk,'independent_tax_field':'capital_tax_evidence_level',
   'independent_tax_literal':ik,'independent_direct_statement_field':'direct_premium_source_and_no_tax_statement','independent_direct_literal':direct}
  if code=='SZ002831':
   per10={'primary_cash_per10_original_shares_CNY':'cash_per_10_original_shares_CNY','primary_capital_per10_original_shares':'capital_per_10_original_shares'}
   need(all(a[x]==b[y] for x,y in per10.items()),'root/independent final published per10 literal mismatch')
   mapping.update(per10_cash_root_field='primary_cash_per10_original_shares_CNY',per10_cash_independent_field='cash_per_10_original_shares_CNY',
    per10_capital_root_field='primary_capital_per10_original_shares',per10_capital_independent_field='capital_per_10_original_shares')
  # Independent object has the compiler-facing canonical field names. Root
  # counterpart is retained as a complete literal digest and field provenance.
  d=copy.deepcopy(b);d['review_field_mapping']=mapping
  d['review_provenance']={'root_review_sha256':refs['four_root'],'independent_review_sha256':refs['four_independent'],
   'root_document_literal_sha256':digest(a),'independent_document_literal_sha256':digest(b)}
  result[code]=d
 single=reviews['single_root'];si=reviews['single_independent']
 need(si['root_content_review_sha256']==refs['single_root'] and si['critical']==[] and si['important']==[] and
  si['all4pages_independently_text_extracted_and_visually_reviewed'] is True,'single-notice independent/root binding required')
 need(len(single['documents'])==1,'single original notice required');d=copy.deepcopy(single['documents'][0]);verified=si['verified_primary_fields']
 need(d['instrument']=='SH603233' and si['primary_pdf_sha256']==d['sha256'],'single original PDF identity mismatch')
 economic=('instrument','publication_day','record_date','ex_date','cash_payment_date','cash_per_original_share_CNY','stock_per_original_share','capital_per_original_share')
 need(all(d[k]==verified[k] for k in economic),'single root/independent primary economic mismatch')
 d['review_field_mapping']={'economic_fields_compared_to':'verified_primary_fields','root_pdf_sha_field':'documents[0].sha256','independent_pdf_sha_field':'primary_pdf_sha256'}
 d['review_provenance']={'root_review_sha256':refs['single_root'],'independent_review_sha256':refs['single_independent'],
  'root_document_literal_sha256':digest(single['documents'][0]),'independent_verified_fields_literal_sha256':digest(verified)}
 result['SH603233']=d
 return result


def validate_projection(p):
 need(set(p['capital_tax'])==CAPITAL_KEYS|{'SH603596|2026-05-11',MIXED},'five precise2026 capital proofs required')
 need(set(p['unresolved_tax'])=={UNRESOLVED,'SH603606|2026-05-26'} and
  all(x.get('verified_exempt') is False and x.get('strict_tax_admission_resolved') is False for x in p['unresolved_tax'].values()),'two literal unverified tax guards must remain false')
 conditional={MIXED,'SZ002595|2026-05-11'}
 need(all(p['capital_tax'][key].get('verified_exempt') is True for key in p['capital_tax']),'capital source projection flags changed')
 need(all(p['capital_tax'][key].get('evidence_kind')=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE' for key in conditional),'conditional source inference cannot become a direct/statutory statement')
 need(p['capital_tax']['SH603596|2026-05-11']['evidence_kind']=='DIRECT_ISSUER_PREMIUM_SOURCE_AND_TRANSFER_NO_TAX_STATEMENT','newdirect2026 event evidence changed')
 need(p['strict_statutory_capital_tax_certification'] is False and p['fractional_registry_allocation_certified'] is False,'statutory/fractional certification must stay false')
 need(set(p['cash_overrides'])=={'SZ000975|2026-04-24'} and set(p['component_precision_overrides'])=={MIXED} and
  p['component_precision_contract']==CONTRACT and p['cash_override_contract']==CASH_CONTRACT and not p['stock_dividend_tax_bases'],'separate precision contracts and no extra bonus-stock proof required')
 need([source_key(x['instrument'],x['record']) for x in p['supplementary_distributions']]==list(CASH_KEYS)+['SH603233|2026-10-19','SH603605|2026-10-16'],'eight unique cash supplements in original literal-prefix order required')
 need(len(p['documents'])==17 and len({d['file'] for d in p['documents']})==17 and all(d.get('day')==d.get('publication_day',d.get('day')) for d in p['documents']),'canonical publication day and17unique consumed documents required')
 for flag in ('events_compiled','event_compilation_admitted','admitted_for_account_replay','portfolio_returns_computed','actual_FIFO_tax_liability_verified','historical_arrival_verified'):
  need(p[flag] is False,'source metadata must not grant financial/account/PIT admission')
 return True
