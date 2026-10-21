"""Stdlib, read-only corporate-question inventory. No event compilation/admission.

Preparation: --self-test reads only synthetic dictionaries. Actual inventory must
wait for the caller's terminal raw/reassembly audit authorization and use an unused
--output. No production modules, network, SDK, prices-to-entitlements or returns.
"""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal as D
from pathlib import Path

START, BOUNDARY, YEAR, END = '2023-12-29', '2025-12-31', '2026-01-01', '2026-10-20'
ROOTS = {
 'low-beta60-corporate-reviewed-horizon-20261021/reviewed-manifest.json':'01dcd1f8e96c544243ee88c446075cdaf68e8fd772dc45813144c85094251c0a',
 'low-beta60-corporate-reviewed-2026-20261021/reviewed-manifest.json':'7fdec0f62c3a83842c9e447a19416d9dd4b4165a44669484822e9d841c5a7d80',
 'szse-value-momentum-full-reviewed-proofs-20261021.json':'ac0cf40ccc3dc1d4ab3a723bfcd1e75cb34f51cac3068bba879b12033a09b9d8',
 'szse-value-full-corporate-notices-20261017/reviewed-manifest.json':'0c14b8e9bfa421a20b5bb6b1befd4b8c0c7c93e674b9f87e910394efacd64723',
 'return-family-corporate-notices-20261017/reviewed-manifest.json':'a77d0caf8788616fee773c1c4e5a0b9614956cbd0f79732644fee0b0b85b1bd8',
 'reversal-full-corporate-notices-20261017/reviewed-manifest.json':'ff7d6c9e1a17978c74d204a616f1bd965600a5605d02667570256d881ccbf022',
}
REVIEWS = {
 'experiments/qlib/low-beta60-horizon-primary-content-review.json':'66fd7313d11a9ed1ed60c48121b904baed9a915a2a2c49fc2847ee978a73168b',
 'experiments/qlib/low-beta60-2026-corporate-content-review.json':'8a78937656054e77e4107a13d85d7d8475a1d1d1c2bfb11caba64cabc563c960',
 'experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json':'0b1f5dc599412f0b0e37fbe11e6a4ab508519e9320b848858aa05bae4e0cc4ec',
 'experiments/qlib/szse-value-momentum-noncash-2026-content-review.json':'eadbd5d0262d2780040e2bf5e835ccfa427f2254be7aaaf4a0cc53f5cde290b7',
}
OLD_RAW = 'price-delay-raw-dev-20261021'
OLD_EVENTS = 'price-delay-account-source-events-20261021'
OLD = {
 OLD_RAW+'/manifest.json':'b179d4e987ad2ee93d0b152d817486c29737c6d605abdad1a15c3fd4713d6b67',
 OLD_RAW+'/calendar.json':'8675b1a13704262b666f552e5fee1cbe084fe1392aa9ce32d53a40b482698c2a',
 'price-delay-pre2026-formations-20261021/targets.json':'03acf78c10c10376b5764b0d1399d1631af08a608aa865575aa1bd56203fad0c',
 OLD_EVENTS+'/derived_events.json':'465bab82c1a2c9b8566011230a3858946ef23667c4ba04e5248b088f6b0e70d0',
 OLD_EVENTS+'/event_source_receipts.json':'a1de87c2f69544e92256e4c534ecf8d6dad5a3c49291302cd2d6b71269e51cc5',
 OLD_EVENTS+'/summary.json':'e3b7f480e44e8cd83d9147efdda705c172bdf9bf4d82617a0b79324da1a51b0c',
 'price-delay-event-source-independent-audit-20261021.json':'934b8a825b3d4662f7bd8f54fb87c6136801a71aee4efd99db7a9ae74af7d201',
}
DECIMAL = re.compile(r'[0-9]+(?:\.[0-9]+)?\Z')


def require(ok, reason):
 if not ok: raise ValueError(reason)


def zero_findings(value):
 return (type(value) is int and value==0) or (type(value) is list and len(value)==0)


def validate_raw_audit_flags(audit,manifest):
 if 'critical_or_important_findings' in audit:
  require(zero_findings(audit['critical_or_important_findings']),'independent raw audit has findings or unsupported zero-findings format')
 if 'local_assembly_complete' in manifest:
  require(manifest['local_assembly_complete'] is True,'local raw assembly incomplete')
 if 'all203_packets_676_sessions_verified' in audit:
  require(audit['all203_packets_676_sessions_verified'] is True,'independent raw audit does not verify complete203/676 source')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def digest(v):
 return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def safe(root, relative):
 p=Path(relative)
 require(not p.is_absolute() and '..' not in p.parts,'unsafe source-relative artifact path')
 return Path(root)/p


def day(text):
 require(isinstance(text,str) and date.fromisoformat(text).isoformat()==text,'noncanonical source date')
 return text


def number(text):
 if not isinstance(text,str) or not DECIMAL.fullmatch(text):return None
 value=D(text)
 return value if value.is_finite() and value>=0 else None


def event_key(code,row):return code+'|'+day(row['dividOperateDate'])


def split_distributions(code,packet,old_codes):
 active=[];excluded=[];other=[]
 for i,row in enumerate(packet['distributions']):
  at=day(row['dividOperateDate']);item={'instrument':code,'row_index':i,'event_key':code+'|'+at,'source_row_sha256':digest(row),'source_row':row}
  if YEAR<=at<=END:active.append(item)
  elif at<YEAR and code not in old_codes:excluded.append({**item,'classification':'OUT_OF_ACCOUNT_SCOPE_FUTURE_ONLY_PRE2026'})
  elif at>END:other.append({**item,'classification':'DISTRIBUTION_OUTSIDE_FIXED_HORIZON_REQUIRES_QUARANTINE'})
 return active,excluded,other


def component_questions(row):
 issues=[];cash=number(row.get('dividCashPsBeforeTax',''));stock=number(row.get('dividStocksPs',''));capital=number(row.get('dividReserveToStockPs',''))
 if cash is None:issues.append('CASH_COMPONENT_BLANK_OR_NONCANONICAL')
 if stock is None:issues.append('STOCK_COMPONENT_BLANK_OR_NONCANONICAL')
 display=row.get('dividCashStock','')
 cash_only=(cash is not None and cash>0 and stock==0 and display.startswith('10派') and
   '送' not in display and '转' not in display and not row.get('dividStockMarketDate'))
 if capital is None:
  issues.append('BLANK_CAPITAL_EXPLICIT_CASH_ONLY_ZERO_CANDIDATE' if row.get('dividReserveToStockPs','')=='' and cash_only else 'CAPITAL_COMPONENT_BLANK_OR_NONCANONICAL_UNRESOLVED')
 if stock is not None and stock>0:issues.append('STOCK_DIVIDEND_TAX_BASIS_REVIEW_REQUIRED')
 if capital is not None and capital>0:issues.append('CAPITAL_TRANSFER_TAX_EVIDENCE_REVIEW_REQUIRED')
 return issues


def coverage_questions(code,packet,sessions,source_exdates,primary_missing):
 """Questions from explicit 2026 source coordinates; never calculate entitlements."""
 questions=[];rows=[r for r in packet['bars'] if BOUNDARY<=r['date']<=END]
 require(rows and rows[0]['date']==BOUNDARY,'missing Dec31 reference boundary: '+code)
 indices={r['date']:i for i,r in enumerate(rows)};previous=None;previous_day=None
 for r in rows:
  at=day(r['date']);close=number(r.get('close',''));reference=number(r.get('preclose',''))
  if at>=YEAR and previous is not None and reference is not None and reference>0 and abs(reference-previous)>D('.005'):
   if at not in source_exdates:
    questions.append({'classification':'RAW_PRECLOSE_WITHOUT_VENDOR_EVENT','instrument':code,'day':at,'previous_valid_close_day':previous_day,
     'previous_valid_close':str(previous),'raw_preclose':str(reference),'bar_sha256':digest(r),'bar':r,
     'existing_primary_supplement_candidate_keys':[code+'|'+at] if at in primary_missing else [],'entitlement_inferred_from_price':False})
  if close is not None and close>0:previous=close;previous_day=at
 for a in packet['adjustments']:
  at=day(a['dividOperateDate'])
  if not YEAR<=at<=END:continue
  i=indices.get(at);previous_session=rows[i-1]['date'] if i is not None and i>0 else None
  if at in source_exdates:status='ADJUSTMENT_SAME_DAY_VENDOR_EVENT_SOURCE_LABEL_ONLY'
  elif previous_session in source_exdates:status='LATE_FACTOR_EXISTING_EARLIER_VENDOR_DIVIDEND_ONLY_SEMANTICS_UNKNOWN'
  else:status='ADJUSTMENT_WITHOUT_VENDOR_DISTRIBUTION_PRIMARY_EVIDENCE_REQUIRED'
  questions.append({'classification':status,'instrument':code,'day':at,'adjustment_row':a,'source_row_sha256':digest(a),
   'previous_explicit_session':previous_session,'existing_primary_supplement_candidate_keys':[code+'|'+at] if at in primary_missing else [],
   'adjustment_date_semantics_verified':False,'entitlement_inferred_from_factor':False,'new_cash_or_share_event_created':False})
 return questions


def matching_facts(row,candidate):
 """Metadata correspondence only, deliberately never returns financial admission."""
 proof=candidate['proof'];kind=candidate['proof_kind'];checks={}
 if kind=='PRIMARY_SUPPLEMENT_CANDIDATE':
  fields=('code','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate')
  expected=proof['record']
  checks.update({field:row.get(field,'')==expected.get(field,'') for field in fields})
  for field in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'):
   checks[field]=number(row.get(field,'')) is not None and number(row.get(field,''))==number(expected.get(field,''))
 elif kind=='PRIMARY_CASH_PRECISION_CANDIDATE':
  checks['literal_vendor_row_digest']=proof.get('source_row_sha256')==digest(row)
  checks['expected_vendor_cash']=number(row.get('dividCashPsBeforeTax',''))==number(proof.get('expected_vendor_cash_per_share',''))
  cash=number(row.get('dividCashPsBeforeTax',''));effective=number(proof.get('effective_cash_per_share',''))
  checks['cash_only']=number(row.get('dividStocksPs',''))==0 and number(row.get('dividReserveToStockPs','') or '0')==0 and not row.get('dividStockMarketDate')
  checks['precision_completion']=cash is not None and effective is not None and effective>cash and effective.quantize(D(1).scaleb(cash.as_tuple().exponent),rounding='ROUND_DOWN')==cash
 elif kind=='CAPITAL_TAX_PROOF_CANDIDATE':
  checks['positive_vendor_capital']=number(row.get('dividReserveToStockPs','')) is not None and number(row['dividReserveToStockPs'])>0
  if 'expected_capital_per_share' in proof:checks['expected_capital']=number(row.get('dividReserveToStockPs',''))==number(proof['expected_capital_per_share'])
 elif kind=='STOCK_TAX_BASIS_PROOF_CANDIDATE':
  checks['expected_positive_stock']=number(row.get('dividStocksPs',''))==number(proof.get('expected_stock_per_original_share','')) and number(row.get('dividStocksPs','')) is not None and number(row['dividStocksPs'])>0
  checks['positive_taxable_income']=number(proof.get('taxable_income_per_original_share','')) is not None and number(proof['taxable_income_per_original_share'])>0
 elif kind=='UNRESOLVED_TAX_LITERAL_GUARD':checks['verified_exempt_stays_false']=proof.get('verified_exempt') is False
 elif kind=='DOCUMENT_METADATA_ONLY_CANDIDATE':
  mapping={'record_date':'dividRegistDate','ex_date':'dividOperateDate','cash_payment_date':'dividPayDate','stock_listing_date':'dividStockMarketDate'}
  for field,rfield in mapping.items():
   if field in proof:checks[field]=(proof[field] or '')==row.get(rfield,'')
  mapping={'cash_per_original_share_CNY':'dividCashPsBeforeTax','stock_per_original_share':'dividStocksPs','capital_per_original_share':'dividReserveToStockPs'}
  for field,rfield in mapping.items():
   if field in proof:checks[field]=number(proof[field]) is not None and number(proof[field])==number(row.get(rfield,'') or ('0' if rfield=='dividReserveToStockPs' else ''))
 source_doc=candidate.get('primary_documents',[])
 if source_doc and kind!='UNRESOLVED_TAX_LITERAL_GUARD':
  checks['announcement_day']=any(d['document'].get('day',d['document'].get('publication_day'))==row.get('dividPlanDate') for d in source_doc)
 return {'metadata_checks':checks,'metadata_conflicts':[key for key,value in checks.items() if value is False],
  'correspondence_status':'METADATA_CONFLICT_REQUIRES_REVIEW' if any(v is False for v in checks.values()) else 'METADATA_CANDIDATE_ONLY_REQUIRES_SOURCE_ROW_AND_CONTENT_ADMISSION',
  'source_receipt_chain_revalidation_required':True,'financial_admission_granted':False}


def self_test():
 code='SH600000';row={'code':'sh.600000','dividPlanDate':'2026-06-01','dividRegistDate':'2026-06-03','dividOperateDate':'2026-06-04','dividPayDate':'2026-06-04','dividStockMarketDate':'','dividCashPsBeforeTax':'0.5','dividStocksPs':'0','dividReserveToStockPs':'','dividCashStock':'10派5元'}
 rejected={}
 def check(label,ok):require(ok,'self-test failed: '+label);rejected[label]=True
 check('blank_capital_without_cash_only_evidence_flagged','CAPITAL_COMPONENT_BLANK_OR_NONCANONICAL_UNRESOLVED' in component_questions({**row,'dividCashStock':'UNKNOWN'}))
 check('blank_capital_cash_only_is_candidate_not_silent_proof',component_questions(row)==['BLANK_CAPITAL_EXPLICIT_CASH_ONLY_ZERO_CANDIDATE'])
 check('positive_stock_requires_tax_basis','STOCK_DIVIDEND_TAX_BASIS_REVIEW_REQUIRED' in component_questions({**row,'dividStocksPs':'0.3'}))
 check('positive_capital_requires_tax_review','CAPITAL_TRANSFER_TAX_EVIDENCE_REVIEW_REQUIRED' in component_questions({**row,'dividReserveToStockPs':'0.4'}))
 oldrow={**row,'dividOperateDate':'2025-06-04'}
 active,excluded,_=split_distributions(code,{'distributions':[oldrow,row]},set())
 check('future_only_pre2026_not_active',len(active)==1 and len(excluded)==1 and excluded[0]['source_row']==oldrow)
 cand={'proof_kind':'PRIMARY_SUPPLEMENT_CANDIDATE','proof':{'record':row},'primary_documents':[]}
 result=matching_facts({**row,'dividCashPsBeforeTax':'0.497403'},cand)
 check('reference_cash_does_not_match_primary_entitlement','dividCashPsBeforeTax' in result['metadata_conflicts'])
 check('PDF_presence_does_not_grant_admission',matching_facts(row,cand)['financial_admission_granted'] is False)
 p={'bars':[{'date':BOUNDARY,'close':'10','preclose':'10'},{'date':'2026-01-05','close':'9.5','preclose':'9.5'},{'date':'2026-01-06','close':'9.6','preclose':'9.5'}],
    'adjustments':[{'dividOperateDate':'2026-01-06','foreAdjustFactor':'0.95'}]}
 q=coverage_questions(code,p,[BOUNDARY,'2026-01-05','2026-01-06'],{'2026-01-05'},set())
 check('late_factor_not_second_entitlement',len(q)==1 and q[0]['classification'].startswith('LATE_FACTOR') and q[0]['new_cash_or_share_event_created'] is False)
 q=coverage_questions(code,p,[BOUNDARY,'2026-01-05','2026-01-06'],set(),set())
 check('preclose_and_unmatched_factor_remain_questions',any(x['classification']=='RAW_PRECLOSE_WITHOUT_VENDOR_EVENT' for x in q) and any(x['classification'].startswith('ADJUSTMENT_WITHOUT') for x in q))
 try:coverage_questions(code,{**p,'bars':p['bars'][1:]},[],set(),set())
 except ValueError:rejected['missing_Dec31_boundary_rejected']=True
 else:raise ValueError('missing boundary accepted')
 precision={'proof_kind':'PRIMARY_CASH_PRECISION_CANDIDATE','proof':{'source_row_sha256':'0'*64,'expected_vendor_cash_per_share':'0.5','effective_cash_per_share':'0.497403'},'primary_documents':[]}
 result=matching_facts(row,precision)
 check('wrong_source_digest_and_reference_precision_rejected',{'literal_vendor_row_digest','precision_completion'}<=set(result['metadata_conflicts']))
 check('zero_findings_integer_and_empty_list_accepted',zero_findings(0) and zero_findings([]))
 for label,value in [('bool_false',False),('bool_true',True),('float_zero',0.0),('string_zero','0'),
     ('null',None),('dict',{}),('nonzero_int',1),('negative_int',-1),('nonempty_list',[{}])]:
  check('zero_findings_'+label+'_rejected',not zero_findings(value))
 validate_raw_audit_flags({'critical_or_important_findings':[], 'all203_packets_676_sessions_verified':True},{'local_assembly_complete':True})
 check('literal_true_complete_assembly_and_raw_audit_accepted',True)
 for field,location in [('local_assembly_complete','manifest'),('all203_packets_676_sessions_verified','audit')]:
  for suffix,value in [('false',False),('int_one',1),('null',None),('string_true','true')]:
   audit={'critical_or_important_findings':0};manifest={}
   (manifest if location=='manifest' else audit)[field]=value
   try:validate_raw_audit_flags(audit,manifest)
   except ValueError:rejected[field+'_'+suffix+'_rejected']=True
   else:raise ValueError('invalid source-completion flag accepted')
 return rejected


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true')
 for name in ('source-root','repo-root','raw-dir','raw-audit','expected-raw-audit-sha256','targets','expected-targets-sha256','output'):parser.add_argument('--'+name)
 args=parser.parse_args()
 if args.self_test:
  require(all(getattr(args,n.replace('-','_')) is None for n in ('source-root','repo-root','raw-dir','raw-audit','expected-raw-audit-sha256','targets','expected-targets-sha256','output')),'self-test must be synthetic only')
  print(json.dumps({'status':'SYNTHETIC_SOURCE_INVENTORY_CONTROLS_PASSED_NO_SOURCE_DATA_READ','negative_controls_rejected':self_test()},indent=2));return
 require(all(getattr(args,n.replace('-','_')) for n in ('source-root','repo-root','raw-dir','raw-audit','expected-raw-audit-sha256','targets','expected-targets-sha256','output')),'all authenticated actual-inventory arguments required')
 base=Path(args.source_root).resolve();repo=Path(args.repo_root).resolve();raw=Path(args.raw_dir).resolve();out=Path(args.output)
 require(not out.exists(),'preserve previous inventory');snapshots={}
 def auth(path,h):
  path=Path(path);require(sha(path)==h,'changed authenticated bytes: '+str(path));snapshots[str(path)]=h
 for n,h in OLD.items():auth(safe(base,n),h)
 for n,h in ROOTS.items():auth(safe(base,n),h)
 for n,h in REVIEWS.items():auth(safe(repo,n),h)
 old_manifest=read(base/OLD_RAW/'manifest.json');old_summary=read(base/OLD_EVENTS/'summary.json')
 for n,h in old_summary['artifact_sha256'].items():auth(safe(base/OLD_EVENTS,n),h)
 old_events=read(base/OLD_EVENTS/'derived_events.json');old_receipts=read(base/OLD_EVENTS/'event_source_receipts.json')
 require(len(old_events)==len(old_receipts)==378 and old_summary['compiled_events']==378,'old378 event/receipt baseline changed')
 require([r['instrument']+'|'+r['ex_date'] for r in old_receipts if r['requires_zero_record_ownership_if_tax_unverified']]==['SH603596|2024-05-20'],'old unknown-tax guard changed')
 auth(args.raw_audit,args.expected_raw_audit_sha256);raw_audit=read(args.raw_audit);manifest=read(raw/'manifest.json');raw_manifest_sha=sha(raw/'manifest.json');auth(raw/'manifest.json',raw_manifest_sha)
 require(any(raw_audit.get(k)==raw_manifest_sha for k in ('manifest_sha256','raw_manifest_sha256','V2_manifest_sha256')),'independent raw audit must bind this exact manifest')
 validate_raw_audit_flags(raw_audit,manifest)
 require(len(manifest['per_code_sha256'])==203,'203 packets required; terminal incomplete capture is not full inventory input')
 if 'capture_complete' in manifest:require(manifest['capture_complete'] is True,'incomplete raw source')
 auth(raw/'calendar.json',manifest['calendar_sha256']);sessions=read(raw/'calendar.json')['sessions'];old_sessions=read(base/OLD_RAW/'calendar.json')['sessions']
 require(len(sessions)==676 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END] and sessions[:486]==old_sessions,'complete calendar and old prefix required')
 auth(args.targets,args.expected_targets_sha256);targets=read(args.targets)
 if 'price_delay_d1' in targets:targets=targets['price_delay_d1']
 old_targets=read(base/'price-delay-pre2026-formations-20261021/targets.json')['price_delay_d1']
 require(len(targets)==34 and {d:t for d,t in targets.items() if d<YEAR}==old_targets,'34 formations with exactold24 prefix required')
 require(all(d in sessions and t['as_of'] in sessions and t['as_of']<d for d,t in targets.items()),'target timing outside explicit calendar')
 codes={c for t in targets.values() for c in t['weights']};old_codes=set(old_manifest['per_code_sha256']);future=codes-old_codes
 require(len(codes)==203 and len(old_codes)==151 and old_codes<=codes and len(future)==52 and codes==set(manifest['per_code_sha256']),'203=151+52 name identity mismatch')
 if 'target_sha256' in manifest:require(manifest['target_sha256']==args.expected_targets_sha256,'raw/target binding mismatch')
 packets={};old_prefixes={}
 for code,h in sorted(manifest['per_code_sha256'].items()):
  require(re.fullmatch(r'(SH|SZ)[0-9]{6}',code) is not None,'invalid packet instrument')
  p=raw/'codes'/(code+'.json');auth(p,h);packet=read(p)
  require(packet['instrument']==code and packet['window']==[START,END] and [r['date'] for r in packet['bars']]==sessions,'complete raw identity/calendar required: '+code)
  packets[code]=packet
  if code in old_codes:
   p=base/OLD_RAW/'codes'/(code+'.json');auth(p,old_manifest['per_code_sha256'][code]);original=read(p)
   checks={field:[r for r in packet[field] if day(r[datefield])<YEAR]==original[field] for field,datefield in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]}
   require(all(checks.values()),'original151 source prefix changed: '+code);old_prefixes[code]=checks
 # Resolve original cached PDF paths only inside the six fixed roots/directories.
 roots={name:read(base/name) for name in ROOTS};documents=[];docs_by_hash={}
 for name,proofs in roots.items():
  for document in proofs.get('documents',[]):
   filename=document['file'];require(Path(filename).name==filename,'unsafe primary filename')
   path=Path(document['source_path']).resolve() if document.get('source_path') else (base/name).parent/filename
   if name=='szse-value-momentum-full-reviewed-proofs-20261021.json' and not document.get('source_path'):
    path=base/'low-beta60-corporate-reviewed-horizon-20261021'/filename
   require(path.resolve().is_relative_to(base),'primary PDF outside fixed source root');auth(path,document['sha256'])
   item={'reviewed_manifest_file':str(base/name),'reviewed_manifest_sha256':ROOTS[name],
    'primary_PDF_file':str(path),'primary_PDF_sha256':document['sha256'],'document':document,'PDF_bytes_authenticated':True,
    'source_receipt_chain_revalidation_required':True,'financial_admission_granted':False}
   documents.append(item);docs_by_hash.setdefault(document['sha256'],[]).append(item)
 candidates={}
 def add(key,kind,proof,name):
  code,at=key.split('|');day(at)
  if not YEAR<=at<=END or code not in codes:return
  refs=[]
  for field in ('source_sha256',):
   if proof.get(field):refs.extend(docs_by_hash.get(proof[field],[]))
  if kind=='UNRESOLVED_TAX_LITERAL_GUARD':
   for part in ('implementation','supplement'):
    if proof.get(part,{}).get('source_sha256'):refs.extend(docs_by_hash.get(proof[part]['source_sha256'],[]))
  require(refs,'proof lacks authenticated registered original PDF: '+key)
  candidates.setdefault(key,[]).append({'event_key':key,'proof_kind':kind,'proof':proof,'proof_sha256':digest(proof),
    'reviewed_manifest_file':str(base/name),'reviewed_manifest_sha256':ROOTS[name],'primary_documents':refs,
    'evidence_kind_preserved':proof.get('evidence_kind',proof.get('basis',proof.get('evidence'))),
    'source_receipt_chain_revalidation_required':True,'financial_admission_granted':False})
 for name,proofs in roots.items():
  for field,kind in [('capital_tax','CAPITAL_TAX_PROOF_CANDIDATE'),('stock_dividend_tax_bases','STOCK_TAX_BASIS_PROOF_CANDIDATE'),
    ('cash_overrides','PRIMARY_CASH_PRECISION_CANDIDATE'),('unresolved_tax','UNRESOLVED_TAX_LITERAL_GUARD')]:
   for key,proof in proofs.get(field,{}).items():add(key,kind,proof,name)
  for proof in proofs.get('supplementary_distributions',[]):add(event_key(proof['instrument'],proof['record']),'PRIMARY_SUPPLEMENT_CANDIDATE',proof,name)
  for doc in proofs.get('documents',[]):
   if doc.get('instrument') and doc.get('ex_date'):
    proof={**doc,'source_sha256':doc['sha256']};add(doc['instrument']+'|'+doc['ex_date'],'DOCUMENT_METADATA_ONLY_CANDIDATE',proof,name)
 active=[];excluded=[];questions=[]
 for code,packet in sorted(packets.items()):
  a,e,other=split_distributions(code,packet,old_codes);active.extend(a);excluded.extend(e);questions.extend(other)
 vendor_keys=Counter(x['event_key'] for x in active)
 for key,count in sorted(vendor_keys.items()):
  if count>1:questions.append({'classification':'DUPLICATE_OR_REVISED_VENDOR_EVENT_REQUIRES_RESOLUTION','event_key':key,'row_count':count})
 primary_missing={key for key,entries in candidates.items() if key not in vendor_keys and any(c['proof_kind']=='PRIMARY_SUPPLEMENT_CANDIDATE' for c in entries)}
 for item in active:
  key=item['event_key'];row=item['source_row'];code=item['instrument'];item['packet_sha256']=manifest['per_code_sha256'][code]
  item['component_questions']=component_questions(row);item['primary_matches']=[]
  if row.get('code')!=code[:2].lower()+'.'+code[2:]:item['component_questions'].append('SOURCE_INSTRUMENT_MISMATCH')
  for field in ('dividPlanDate','dividRegistDate','dividPayDate','dividStockMarketDate'):
   if row.get(field):day(row[field])
  if not row.get('dividRegistDate') or not row.get('dividPlanDate') or not row['dividPlanDate']<row['dividRegistDate']<row['dividOperateDate']:
   item['component_questions'].append('INVALID_OR_MISSING_RECORD_ANNOUNCEMENT_TIMING')
  if row.get('dividRegistDate','')<YEAR:item['component_questions'].append('CROSS_YEAR_RECORD_EX_BOUNDARY_REQUIRES_EXPLICIT_RESOLUTION')
  if row.get('dividRegistDate') not in sessions:item['component_questions'].append('RECORD_DATE_NOT_IN_EXPLICIT_SESSIONS')
  for c in candidates.get(key,[]):item['primary_matches'].append({**c,**matching_facts(row,c)})
  kinds={c['proof_kind'] for c in item['primary_matches'] if not c['metadata_conflicts']}
  if number(row.get('dividReserveToStockPs','')) not in (None,D(0)):
   if 'UNRESOLVED_TAX_LITERAL_GUARD' in kinds:item['component_questions'].append('LITERAL_UNRESOLVED_CAPITAL_TAX_ZERO_RECORD_OWNERSHIP_REQUIRED')
   elif 'CAPITAL_TAX_PROOF_CANDIDATE' not in kinds:item['component_questions'].append('NO_FIXED_LOCAL_CAPITAL_TAX_PROOF_ZERO_RECORD_OWNERSHIP_REQUIRED')
  if number(row.get('dividStocksPs','')) not in (None,D(0)) and 'STOCK_TAX_BASIS_PROOF_CANDIDATE' not in kinds:
   item['component_questions'].append('NO_FIXED_LOCAL_STOCK_TAX_BASIS_ZERO_RECORD_OWNERSHIP_REQUIRED')
  if item['component_questions'] or any(c['metadata_conflicts'] for c in item['primary_matches']):
   questions.append({'classification':'VENDOR_EVENT_COMPONENT_OR_PRIMARY_MATCH_QUESTION',**item})
 for code,packet in sorted(packets.items()):
  exdates={x['source_row']['dividOperateDate'] for x in active if x['instrument']==code}
  missingdays={key.split('|')[1] for key in primary_missing if key.startswith(code+'|')}
  for q in coverage_questions(code,packet,sessions,exdates,missingdays):
   key=code+'|'+q['day'];q['local_primary_candidates']=candidates.get(key,[])
   if q['classification'].startswith('LATE_FACTOR'):
    q['earlier_vendor_event_key']=code+'|'+q['previous_explicit_session'];q['earlier_event_primary_candidates']=candidates.get(q['earlier_vendor_event_key'],[])
   questions.append(q)
  for i,item in enumerate(packet.get('quarantine',[])):
   record=item.get('record',{});at=record.get('dividOperateDate','')
   if at:day(at)
   status=('FUTURE_ONLY_PRE2026_QUARANTINE_OUT_OF_ACCOUNT_SCOPE' if code in future and at and at<YEAR else
     'AFTER_HORIZON_QUARANTINE_NOT_INVESTMENT_INPUT' if at and at>END else
     'BEFORE_SOURCE_WINDOW_QUARANTINE_NOT_INVESTMENT_INPUT' if at and at<START else
     'IN_SCOPE_OR_UNDATED_QUARANTINE_REQUIRES_SOURCE_RESOLUTION')
   questions.append({'classification':status,'instrument':code,'quarantine_index':i,'quarantine_entry':item,'source_entry_sha256':digest(item),
    'local_primary_candidates':candidates.get(code+'|'+at,[]) if at else []})
 for key in sorted(primary_missing):
  questions.append({'classification':'LOCAL_PRIMARY_SUPPLEMENT_CANDIDATE_WITH_NO_VENDOR_EVENT','event_key':key,
   'local_primary_candidates':candidates[key],'new_event_compiled':False,'financial_admission_granted':False})
 controls=self_test()
 for p,h in snapshots.items():require(sha(p)==h,'authenticated input changed during inventory: '+p)
 excluded_per_code={code:sum(x['instrument']==code for x in excluded) for code in sorted(future)}
 excluded_adjustments=[];excluded_bar_prefixes={}
 for code in sorted(future):
  for i,row in enumerate(packets[code]['adjustments']):
   if day(row['dividOperateDate'])<YEAR:
    excluded_adjustments.append({'instrument':code,'row_index':i,'source_row':row,'source_row_sha256':digest(row),
      'classification':'FUTURE_ONLY_PRE2026_ADJUSTMENT_NOT_AN_ACCOUNT_ENTITLEMENT'})
  before=[r for r in packets[code]['bars'] if r['date']<YEAR]
  excluded_bar_prefixes[code]={'pre2026_bar_count':len(before),'literal_rows_digest':digest(before),
    'pre2026_bars_create_account_ownership_or_entitlements':False,'Dec31_boundary_retained_for_2026_reference_check':True}
 unknown_capital=[x['event_key'] for x in active if any('ZERO_RECORD_OWNERSHIP_REQUIRED' in c and 'CAPITAL' in c for c in x['component_questions'])]
 unknown_stock=[x['event_key'] for x in active if any('ZERO_RECORD_OWNERSHIP_REQUIRED' in c and 'STOCK' in c for c in x['component_questions'])]
 result={'status':'INDEPENDENT_PRICE_DELAY_203_NAME_HORIZON_CORPORATE_QUESTION_INVENTORY_NOT_EVENT_OR_ACCOUNT_ADMISSION',
  'audit_code_sha256':sha(__file__),'window':[START,END],'raw_manifest_sha256':raw_manifest_sha,
  'independent_raw_audit_file':str(Path(args.raw_audit)),'independent_raw_audit_sha256':args.expected_raw_audit_sha256,
  'targets_sha256':args.expected_targets_sha256,'names':203,'original_names':151,'future_only_names':52,'sessions':676,'targets':34,
  'original378_event_file_sha256':OLD[OLD_EVENTS+'/derived_events.json'],'original378_receipt_file_sha256':OLD[OLD_EVENTS+'/event_source_receipts.json'],
  'original378_event_objects_ids_order_receipts_and_source_files_unchanged':True,'original151_raw_prefix_checks':old_prefixes,
  'old_unverified_tax_guard_retained':'SH603596|2024-05-20','actual_zero_record_ownership_verified':False,
  'fixed_local_proof_allowlist_sha256':ROOTS,'fixed_public_content_review_sha256':REVIEWS,
  'original_PDF_references_authenticated':len(documents),'PDF_authentication_is_financial_admission':False,
  'all_2026_vendor_distribution_rows':active,'all_2026_vendor_distribution_rows_count':len(active),
  'future_only_pre2026_excluded_rows':excluded,'future_only_pre2026_excluded_row_count':len(excluded),
  'all52_future_only_name_excluded_pre2026_row_counts':excluded_per_code,
  'future_only_pre2026_adjustments_excluded_from_account_entitlements':excluded_adjustments,
  'all52_future_only_pre2026_bar_prefixes_not_account_ownership':excluded_bar_prefixes,
  'local_primary_candidates_by_event_key':candidates,'local_primary_supplement_candidates_missing_vendor':sorted(primary_missing),
  'questions':questions,'question_classification_counts':dict(sorted(Counter(x['classification'] for x in questions).items())),
  'new_unresolved_capital_zero_record_ownership_keys':sorted(set(unknown_capital)),
  'new_unresolved_stock_tax_basis_zero_record_ownership_keys':sorted(set(unknown_stock)),
  'SH603233_new_notice_outside_fixed_allowlist_not_assumed_reviewed':True,
  'negative_controls_rejected':controls,'all_bound_inputs_unchanged_after_inventory':True,
  'imports_project_code':False,'new_events_compiled':False,'new_proofs_projected':False,'source_or_repository_modified':False,
  'network_calls':0,'account_or_ROI_run':False,'portfolio_returns_computed':False,'historical_PIT_certified':False,
  'strict_statutory_tax_certification':False,'actual_FIFO_tax_liability_verified':False,'source_or_account_admission':False,
  'limits':['Matching keys/metadata and authentic PDF bytes propose reuse only; source receipt chain and complete economic content must be bound before any new financial proof projection.',
   'No match means only these six fixed local proof roots, not global issuer absence.',
   'Raw reference changes/factors identify questions and never determine amounts, income or inventory.',
   'Unknown tax needs actual record inventory zero in a separately authorized replay; this source inventory never verifies ownership.',
   'New SH603233 capture/review is deliberately outside this fixed allowlist until separately authorized and explicitly hash-bound.']}
 out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
 print('source-only corporate inventory written; no new event compilation or account/ROI')


if __name__=='__main__':main()
