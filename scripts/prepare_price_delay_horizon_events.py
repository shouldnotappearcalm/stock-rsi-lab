"""Frozen thin source-event compiler. No queries, prices/account replay or ROI.

Real execution requires reviewed/pushed method and an externally hashed final
plan. The distributed plan template intentionally cannot authenticate or run.
"""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.prepare_low_beta60_extension_events import compile_append_only,serialize_event
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler_v3 import apply_component_precision,CONTRACT

START,PRE_END,END='2023-12-29','2025-12-31','2026-10-20'
OLD_RAW='price-delay-raw-dev-20261021';RAW='price-delay-raw-horizon-v2-20261021'
OLD_SOURCE='price-delay-account-source-events-20261021';OLD_PDFS='price-delay-corporate-reviewed-20261021'
PROOFS='price-delay-horizon-corporate-reviewed-20261021';OUTPUT='price-delay-account-horizon-events-20261021'
OLD_TARGET='price-delay-pre2026-formations-20261021/targets.json';TARGET='price-delay-horizon-formations-20261021/candidate_targets.json'
UNSAFE=['SH603606|2026-05-26','SZ000937|2026-06-17'];MIXED='SZ002831|2026-06-04'
OLD_AUDIT_SHA='934b8a825b3d4662f7bd8f54fb87c6136801a71aee4efd99db7a9ae74af7d201'
RAW_AUDIT_SHA='a7bf3324200deb497ba93327fe41c2d4e6ae7fb5b39d7ed81916aaca91ded753'
RAW_MANIFEST_SHA='9fe3990c0b4b1c076b78c97971ceecf593687b2f15699154c3bdbbce666f6490'
RAW_REQUEST='experiments/qlib/price-delay-horizon-raw-source-request.json'
ASSEMBLY_REQUEST='experiments/qlib/price-delay-horizon-local-reassembly-request.json'
RAW_AUDIT='experiments/qlib/price-delay-horizon-local-reassembly-independent-audit.json'
FOUR_REVIEW='experiments/qlib/price-delay-horizon-four-primary-independent-review.json'
PROJECTION_AUDIT='experiments/qlib/price-delay-horizon-proof-projection-independent-audit.json'
METHOD_FILES=('scripts/prepare_price_delay_horizon_events.py','scripts/prepare_price_delay_horizon_proofs.py',
 'scripts/price_delay_horizon_proof_projection.py','scripts/prepare_price_delay_account_sources_pre2026.py',
 'scripts/prepare_low_beta60_extension_events.py','scripts/prepare_low_beta60_account_sources.py',
 'src/stock_rsi/distribution_event_compiler_v3.py','src/stock_rsi/distribution_event_compiler_v2.py',
 'src/stock_rsi/distribution_event_compiler.py','src/stock_rsi/stock_distribution_account.py',
 'src/stock_rsi/raw_share_account.py','src/stock_rsi/broker.py','src/stock_rsi/calendar.py',
 'src/stock_rsi/data.py','src/stock_rsi/models.py','src/stock_rsi/time.py')
PUBLIC_FILES=('docs/research/price-delay-horizon-account-continuation-plan-2026-10-21.md',RAW_REQUEST,
 ASSEMBLY_REQUEST,RAW_AUDIT,PROJECTION_AUDIT,'experiments/qlib/price-delay-horizon-four-primary-content-review.json',FOUR_REVIEW,
 'experiments/qlib/price-delay-horizon-single-primary-content-review.json',
 'experiments/qlib/price-delay-horizon-single-primary-independent-review.json')
LOCAL_FILES=(OLD_RAW+'/manifest.json',OLD_RAW+'/calendar.json',RAW+'/manifest.json',RAW+'/calendar.json',OLD_TARGET,TARGET,
 OLD_SOURCE+'/summary.json',OLD_SOURCE+'/effective_proofs.json',OLD_SOURCE+'/derived_events.json',OLD_SOURCE+'/event_source_receipts.json',
 OLD_PDFS+'/reviewed-manifest.json','price-delay-event-source-independent-audit-20261021.json',
 PROOFS+'/reviewed-manifest.json',PROOFS+'/summary.json')
SCOPE={'old_names':151,'names':203,'future_only_names':52,'old_sessions':486,'sessions':676,'old_targets':24,'targets':34,
 'old_events':378,'old_PDFs':15,'new_PDFs':17,'original_financial_files':48}
EXPECTED={'vendor_2026_rows':227,'primary_supplements':8,'future_only_pre2026_rows_excluded':131,'total_events':613}
ARTIFACTS=('derived_events.json','event_source_receipts.json','effective_2026_proofs.json','original_derived_events.json','original_event_source_receipts.json')


def need(ok,reason):
 if not ok:raise ValueError(reason)


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def safe(root,name):
 p=Path(name);root=Path(root).resolve();need(not p.is_absolute() and '..' not in p.parts,'safe relative input path required');out=(root/p).resolve();need(out.is_relative_to(root),'input symlink escaped root');return out

def authenticate_map(root,bindings):
 result={}
 for name,h in bindings.items():
  need(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) is not None,'frozen SHA required, template placeholders cannot run')
  p=safe(root,name);need(sha(p)==h,'frozen input changed: '+str(p));result[str(p)]=h
 return result


def authenticate_financial_files(base,plan_map,original_map):
 need(len(original_map)==48 and plan_map==original_map,'exact original48 financial file map required')
 # Never substitute producer-summary mapping equality for actual artifact bytes.
 return authenticate_map(base,plan_map)


def verify_old_audit_anchor(audit,summary_sha,reviewed_sha,raw_sha):
 need(audit['status']=='INDEPENDENT_378_EVENT_ECONOMICS_IDENTITIES_AND_SOURCE_RECEIPTS_RECONSTRUCTED' and
  audit['events_reconstructed']==378 and audit['all378_economics_dates_event_IDs_and_receipts_identical'] is True and
  audit['summary_sha256']==summary_sha and audit['reviewed_manifest_sha256']==reviewed_sha and
  audit['raw_manifest_sha256']==raw_sha,'original independent378 economic/identity/source anchors changed')
 return True


def verify_projection_audit_anchor(audit,manifest_sha,summary_sha):
 need(audit['reviewed_manifest_sha256']==manifest_sha and audit['summary_sha256']==summary_sha and
  audit['all17_PDFs_byte_exact'] is True and
  audit['all_projected_proof_objects_independently_reconstructed'] is True and
  _zero_findings(audit['critical_or_important_findings']),'independent projection reconstruction/source anchors required')
 return True


def verify_original_producer_links(summary,raw_sha,reviewed_sha,target_sha):
 need(summary['raw_manifest_sha256']==raw_sha and summary['reviewed_manifest_sha256']==reviewed_sha and
  summary['target_sha256']==target_sha,'original source producer raw/reviewed/target links changed')
 return True


def recheck(bindings):
 for path,h in bindings.items():need(sha(path)==h,'authenticated source changed during source compilation: '+path)


def plan_template():
 return {'status':'DRAFT_NOT_FROZEN_OR_EXECUTABLE','window':[START,END],'output_directory':OUTPUT,'scope':SCOPE.copy(),
 'expected_reconstruction':EXPECTED.copy(),'method_code_sha256':{n:'<FREEZE_FINAL_METHOD_SHA256>' for n in METHOD_FILES},
 'public_evidence_sha256':{n:'<FREEZE_FINAL_PUBLIC_SHA256>' for n in PUBLIC_FILES},
 'local_source_sha256':{n:('<PENDING_REVIEWED_PROJECTION_SHA256>' if n.startswith(PROOFS+'/') else '<FREEZE_LOCAL_SHA256>') for n in LOCAL_FILES},
 'primary_document_sha256':{'<EXACT_OLD15_PLUS_NEW17_BASE_RELATIVE_PDF_PATHS>':'<FREEZE_PDF_SHA256>'},
 'financial_artifact_sha256':{'<EXACT48_MAP_FROM_FROZEN_RAW_REQUEST>':'<FREEZE_ORIGINAL_FINANCIAL_SHA256>'},
 'source_queries_allowed':False,'account_replay_to_run':False,'portfolio_returns_to_compute':False,'investment_rule_changes_allowed':False}


def validate_plan(p):
 need(p['status']=='FROZEN_PRICE_DELAY_HORIZON_APPEND_ONLY_SOURCE_EVENTS_NO_ROI' and p['window']==[START,END] and
  p['output_directory']==OUTPUT and p['scope']==SCOPE and p['expected_reconstruction']==EXPECTED,'fixed scope/final frozen plan required')
 for field in ('source_queries_allowed','account_replay_to_run','portfolio_returns_to_compute','investment_rule_changes_allowed'):need(p[field] is False,'no new queries/account/ROI/rule change allowed')
 for field,names in [('method_code_sha256',METHOD_FILES),('public_evidence_sha256',PUBLIC_FILES),('local_source_sha256',LOCAL_FILES)]:
  need(set(p[field])==set(names),'exact fixed binding keys required: '+field)
 for field in ('method_code_sha256','public_evidence_sha256','local_source_sha256','primary_document_sha256','financial_artifact_sha256'):
  need(isinstance(p[field],dict) and all(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) is not None for h in p[field].values()),'unfilled/invalid SHA map: '+field)
 need(len(p['primary_document_sha256'])==32 and len(p['financial_artifact_sha256'])==48,'all32 PDF and48 original financial bindings required')
 return True


def validate_destination(base,out):
 need(Path(out).resolve()==(Path(base)/OUTPUT).resolve() and not Path(out).exists(),'new fixed output required; preserve previous source artifact')


def compile_horizon(old,old_proofs,old_events,old_receipts,packets,proofs,calendar):
 """Real unchanged append compiler, then canonical V3 correction; no replay."""
 before=digest([old,old_proofs,old_events,old_receipts,packets,proofs])
 need(proofs.get('component_precision_contract')==CONTRACT and set(proofs.get('component_precision_overrides',{}))=={MIXED},'only registered2026 mixed precision key permitted')
 need(set(proofs.get('unresolved_tax',{}))==set(UNSAFE) and all(p.get('verified_exempt') is False for p in proofs['unresolved_tax'].values()),'two original2026 unknown tax markers must remain false')
 events,receipts,stats=compile_append_only(old,old_proofs,old_events,old_receipts,packets,proofs,calendar)
 n=len(old_events)
 need([serialize_event(e) for e in events[:n]]==old_events and list(receipts[:n])==old_receipts,'old economic/receipt prefix changed before precision')
 # V3 indexes only current-year rows. Future-only historical distributions must
 # never become correction inputs or cause unrelated old-year event admission.
 current={code:{'instrument':code,'distributions':[r for r in p['distributions'] if '2026-01-01'<=r['dividOperateDate']<=END]} for code,p in packets.items()}
 updated,evidence=apply_component_precision(events,receipts,current,proofs,calendar)
 changed=[e.instrument+'|'+e.ex_date.isoformat() for e,u,r,s in zip(events,updated,receipts,evidence) if e!=u or r!=s]
 corrected=[r['instrument']+'|'+r['ex_date'] for r in evidence if r['source_kind']=='PRIMARY_COMPONENT_PRECISION_CORRECTION']
 need(changed==corrected==[MIXED],'only explicitly registered mixed event economics/receipt may change')
 need([serialize_event(e) for e in updated[:n]]==old_events and list(evidence[:n])==old_receipts,'original event IDs/order/economics/receipts changed after precision')
 unsafe=sorted(r['instrument']+'|'+r['ex_date'] for r in evidence[n:] if r['requires_zero_record_ownership_if_tax_unverified'])
 need(unsafe==stats['unverified_tax_event_keys']==UNSAFE,'new precision must preserve unknown-tax pre-mutation guards')
 vendor=sum(len(p['distributions']) for p in current.values());supp=len(proofs['supplementary_distributions'])
 need(len(updated)==len(evidence)==n+vendor+supp,'actual original/vendor/primary source counts do not reconcile')
 need(before==digest([old,old_proofs,old_events,old_receipts,packets,proofs]),'compiler mutated original sources/proofs')
 return updated,evidence,{**stats,'compiled_events':len(updated),'vendor_2026_rows':vendor,'primary_supplements':supp,
  'corrected_component_event_keys':corrected,'source_kind_counts':dict(Counter(r['source_kind'] for r in evidence)),
  'original_event_objects_ids_order_and_receipts_unchanged':True}


def validate_coverage(old,packets,events):
 """Source-date coverage, not amount inference; no future-only pre26 admission."""
 for old_scope,sources in ((True,old),(False,packets)):
  exs={code:set() for code in sources}
  for e in events:
   if old_scope==(e.ex_date<date(2026,1,1)):
    need(e.instrument in sources,'event outside source coverage scope');exs[e.instrument].add(e.ex_date.isoformat())
  for code,p in sources.items():
   rows=p['bars'] if old_scope else [r for r in p['bars'] if r['date']>=PRE_END]
   need(old_scope or rows and rows[0]['date']==PRE_END,'all2026 sources need Dec31 boundary')
   indices={r['date']:i for i,r in enumerate(rows)};previous=None
   for r in rows:
    reference=Decimal(r['preclose']) if r.get('preclose') else None
    if previous is not None and reference is not None and reference>0 and abs(reference-previous)>Decimal('.005'):
     need(r['date'] in exs[code],'unexplained raw preclose change: '+code+' '+r['date'])
    if r.get('close') and Decimal(r['close'])>0:previous=Decimal(r['close'])
   for a in p['adjustments']:
    at=a['dividOperateDate']
    if not old_scope and at<'2026-01-01':continue
    need(at in indices,'adjustment outside explicit source sessions');i=indices[at]
    need(at in exs[code] or i>0 and rows[i-1]['date'] in exs[code],'unexplained source adjustment without separately dated event')
   for q in p.get('quarantine',[]):
    at=q.get('record',{}).get('dividOperateDate','');reason=q.get('reason')
    if not old_scope and code not in old and at and at<'2026-01-01':continue
    cutoff=PRE_END if old_scope else END
    need(reason in ('AFTER_CAPTURE_CUTOFF','AFTER_EXTENSION_CUTOFF') and at>cutoff or reason in ('BEFORE_CAPTURE_WINDOW','BEFORE_EXTENSION_WINDOW') and at and at<START,'unresolved in-scope quarantine')


def _packets(base,directory,count,end):
 root=base/directory;m=read(root/'manifest.json');s=read(root/'calendar.json')['sessions']
 need(len(s)==count and s==sorted(set(s)) and [s[0],s[-1]]==[START,end] and sha(root/'calendar.json')==m['calendar_sha256'],'explicit source calendar mismatch')
 packets={};bound={}
 for code,h in m['per_code_sha256'].items():
  need(re.fullmatch('(SH|SZ)[0-9]{6}',code) is not None,'canonical source issuer required');path=root/'codes'/(code+'.json');need(sha(path)==h,'original packet SHA changed');bound[str(path.resolve())]=h;p=read(path)
  need(p['instrument']==code and p['window']==[START,end] and [r['date'] for r in p['bars']]==s,'complete original packet/calendar identity required');packets[code]=p
 return m,s,packets,bound


def _tree(base,directory,expected):
 root=base/directory;actual={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
 need(actual==expected,'original source tree changed: '+directory)
 return {str((root/f).resolve()):h for f,h in actual.items()}


def _zero_findings(value):return type(value) is int and value==0 or type(value) is list and not value


def load_inputs(base,repo,plan):
 validate_plan(plan);bound={}
 for field,root in [('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base),
   ('primary_document_sha256',base)]:bound.update(authenticate_map(root,plan[field]))
 rawreq=read(repo/RAW_REQUEST);bound.update(authenticate_financial_files(base,plan['financial_artifact_sha256'],rawreq['immutable_financial_sha256']))
 assembly=read(repo/ASSEMBLY_REQUEST)
 bound.update(_tree(base,'price-delay-raw-horizon-20261021',assembly['immutable_capture_tree_sha256']))
 bound.update(_tree(base,'price-delay-horizon-missing-primary-20261021',assembly['immutable_primary_tree_sha256']))
 four=read(repo/FOUR_REVIEW);fourroot=base/'price-delay-horizon-remaining-primary-20261021';fm=read(fourroot/'manifest.json')
 need(sha(fourroot/'manifest.json')==four['capture_manifest_sha256'] and sha(fourroot/'price-delay-scope.json')==four['scope_sha256'],'new four-primary capture binding mismatch')
 tree={**fm['artifact_sha256'],'manifest.json':four['capture_manifest_sha256'],'price-delay-scope.json':four['scope_sha256']};bound.update(_tree(base,fourroot.name,tree))
 om,os,old,b=_packets(base,OLD_RAW,486,PRE_END);bound.update(b);rm,rs,packets,b=_packets(base,RAW,676,END);bound.update(b)
 need(len(old)==151 and len(packets)==203 and set(old)<=set(packets) and len(set(packets)-set(old))==52 and rs[:486]==os,'fixed original151/full203 source scope required')
 for code,p in old.items():
  for f,k in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:need([r for r in packets[code][f] if r[k]<'2026-01-01']==p[f],'literal original151 source prefix changed')
 need(sha(repo/RAW_AUDIT)==RAW_AUDIT_SHA and sha(base/RAW/'manifest.json')==RAW_MANIFEST_SHA,'fixed independently audited raw-v2 source anchor changed')
 audit=read(repo/RAW_AUDIT)
 need(audit['manifest_sha256']==sha(base/RAW/'manifest.json') and audit['all203_packets_676_sessions_verified'] is True and audit['all151_original_literal_pre2026_prefixes_identical'] is True and
  _zero_findings(audit['critical_or_important_findings']) and rm['local_assembly_complete'] is True,'independent complete V2 source audit required')
 targets=read(base/TARGET);previous=read(base/OLD_TARGET)['price_delay_d1']
 need(len(targets)==34 and len(previous)==24 and {d:t for d,t in targets.items() if d<'2026-01-01'}==previous and {c for t in targets.values() for c in t['weights']}==set(packets),'34target union203 and exact24 prefix required')
 idx={d:i for i,d in enumerate(rs)}
 need(all(d in idx and idx[d]>0 and t['as_of']==rs[idx[d]-1] for d,t in targets.items()),'target snapshot must be previous explicit source session')
 need(rm['target_sha256']==sha(base/TARGET) and om['target_sha256']==sha(base/OLD_TARGET),'new/original raw target binding mismatch')
 olddir=base/OLD_SOURCE;ss=read(olddir/'summary.json')
 need(set(ss['artifact_sha256'])=={'effective_proofs.json','derived_events.json','event_source_receipts.json'},'complete original source artifact set required')
 for name,h in ss['artifact_sha256'].items():need(sha(olddir/name)==h,'original source artifact changed')
 original_audit_path=base/'price-delay-event-source-independent-audit-20261021.json'
 need(sha(original_audit_path)==OLD_AUDIT_SHA,'immutable original378 independent audit bytes changed')
 verify_old_audit_anchor(read(original_audit_path),sha(olddir/'summary.json'),sha(base/OLD_PDFS/'reviewed-manifest.json'),sha(base/OLD_RAW/'manifest.json'))
 verify_original_producer_links(ss,sha(base/OLD_RAW/'manifest.json'),sha(base/OLD_PDFS/'reviewed-manifest.json'),sha(base/OLD_TARGET))
 oldproofs=read(olddir/'effective_proofs.json');oe=read(olddir/'derived_events.json');orr=read(olddir/'event_source_receipts.json')
 need(len(oe)==len(orr)==378,'original378 source events required')
 need([r['instrument']+'|'+r['ex_date'] for r in orr if r['requires_zero_record_ownership_if_tax_unverified']]==['SH603596|2024-05-20'],'original2024 tax guard must remain unverified')
 proofdir=base/PROOFS;proofs=read(proofdir/'reviewed-manifest.json');ps=read(proofdir/'summary.json')
 verify_projection_audit_anchor(read(repo/PROJECTION_AUDIT),sha(proofdir/'reviewed-manifest.json'),sha(proofdir/'summary.json'))
 need(ps['reviewed_manifest_sha256']==sha(proofdir/'reviewed-manifest.json') and ps['raw_manifest_sha256']==proofs['raw_manifest_sha256']==sha(base/RAW/'manifest.json') and
  ps['target_sha256']==proofs['target_sha256']==sha(base/TARGET) and ps['projection_request_sha256']==proofs['projection_request_sha256'] and re.fullmatch('[0-9a-f]{64}',ps['projection_request_sha256']) is not None,'frozen reviewed projection/raw/target/request binding mismatch')
 need(set(ps['artifact_sha256'])=={'reviewed-manifest.json'}|{d['file'] for d in proofs['documents']} and len(ps['artifact_sha256'])==18,'exact eighteen projection output artifacts required')
 for name,h in ps['artifact_sha256'].items():need(Path(name).name==name and sha(proofdir/name)==h,'projection output artifact changed')
 need(proofs['admitted_for_account_replay'] is False and ps['source_admitted_for_account_replay'] is False and
  proofs['portfolio_returns_computed'] is False and ps['portfolio_returns_computed'] is False,'source projection cannot confer account/ROI admission')
 need(proofs['events_compiled'] is False and proofs['component_precision_proof_is_metadata_only'] is True,'reviewed component precision must still be uncompiled source metadata')
 need(set(proofs['capital_tax'])=={'SH601128|2026-06-09','SH603737|2026-06-01','SZ002595|2026-05-11','SH603596|2026-05-11',MIXED} and
  set(proofs['unresolved_tax'])==set(UNSAFE) and set(proofs['cash_overrides'])=={'SZ000975|2026-04-24'} and
  set(proofs['component_precision_overrides'])=={MIXED} and proofs['component_precision_contract']==CONTRACT and
  not proofs['stock_dividend_tax_bases'] and len(proofs['supplementary_distributions'])==8 and proofs['strict_statutory_capital_tax_certification'] is False,'exact new proof scope and precision contracts required')
 need(all(proofs['unresolved_tax'][k]['verified_exempt'] is False for k in UNSAFE),'unknown capital tax upgraded')
 for key in (MIXED,'SZ002595|2026-05-11'):need(proofs['capital_tax'][key]['evidence_kind']=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE','conditional evidence cannot become direct/statutory')
 pdfmap={}
 for p,folder,count in [(oldproofs,OLD_PDFS,15),(proofs,PROOFS,17)]:
  need(len(p['documents'])==count and len({d['file'] for d in p['documents']})==count,'complete distinct old15/new17 original PDFs required')
  for d in p['documents']:
   need(Path(d['file']).name==d['file'],'original PDF basename required');name=folder+'/'+d['file'];pdfmap[name]=d['sha256']
 need(pdfmap==plan['primary_document_sha256'],'exact old15/new17 PDF binding map changed')
 chains=proofs['source_evidence_chains'];chains=list(chains.values()) if isinstance(chains,dict) else chains
 need(len(chains)==17,'all seventeen source evidence chains required')
 for chain in chains:
  files=chain['authenticated_original_files'];need(isinstance(files,dict) and files,'nonempty authenticated original receipt/review/PDF chain map required')
  for name,h in files.items():
   path=Path(name).resolve();need(path.is_relative_to(base.resolve()) or path.is_relative_to(repo.resolve()),'evidence chain outside original source/repo roots')
   need(re.fullmatch('[0-9a-f]{64}',h) is not None and sha(path)==h,'original evidence chain file changed');bound[str(path)]=h
 recheck(bound)
 return {'old_packets':old,'old_proofs':oldproofs,'old_events':oe,'old_receipts':orr,'packets':packets,'proofs':proofs,
  'calendar':TradingCalendar(rs),'bound_files':bound,'old_event_bytes':(olddir/'derived_events.json').read_bytes(),
  'old_receipt_bytes':(olddir/'event_source_receipts.json').read_bytes(),'projection_summary_sha256':sha(proofdir/'summary.json')}


def main(argv=None):
 parser=argparse.ArgumentParser()
 for n in ('source-root','plan','expected-plan-sha256','output-dir'):parser.add_argument('--'+n,required=True)
 parser.add_argument('--repo-root',default=str(Path(__file__).resolve().parents[1]));parser.add_argument('--preflight-only',action='store_true');a=parser.parse_args(argv)
 base,repo,out=Path(a.source_root).resolve(),Path(a.repo_root).resolve(),Path(a.output_dir).resolve();validate_destination(base,out)
 need(re.fullmatch('[0-9a-f]{64}',a.expected_plan_sha256) is not None and sha(a.plan)==a.expected_plan_sha256,'external final request SHA required')
 plan=read(a.plan);x=load_inputs(base,repo,plan)
 if a.preflight_only:
  print('source event preflight passed; no compilation/write/account/ROI');return 0
 events,receipts,stats=compile_horizon(*(x[k] for k in ('old_packets','old_proofs','old_events','old_receipts','packets','proofs','calendar')))
 need(stats['original_events']==378 and stats['vendor_2026_rows']==227 and stats['primary_supplements']==8 and
  stats['earlier_rows_of_future_only_names_ignored']==131 and stats['compiled_events']==613,'actual source reconstruction differs from frozen expectations; never pad/fabricate')
 validate_coverage(x['old_packets'],x['packets'],events);recheck(x['bound_files']);need(sha(a.plan)==a.expected_plan_sha256,'event request changed during compilation')
 out.mkdir(exist_ok=False)
 try:
  artifacts={'derived_events.json':[serialize_event(e) for e in events],'event_source_receipts.json':list(receipts),'effective_2026_proofs.json':x['proofs']}
  for name,value in artifacts.items():
   with (out/name).open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
  for name,value in [('original_derived_events.json',x['old_event_bytes']),('original_event_source_receipts.json',x['old_receipt_bytes'])]:
   with (out/name).open('xb') as f:f.write(value)
  recheck(x['bound_files']);need(sha(a.plan)==a.expected_plan_sha256,'external event request changed before summary')
  summary={'status':'PRICE_DELAY_HORIZON_SOURCE_EVENTS_COMPILED_OLD378_UNCHANGED_INDEPENDENT_AUDIT_PENDING',
   'plan_sha256':a.expected_plan_sha256,'window':[START,END],**stats,'scope':SCOPE,'method_code_sha256':plan['method_code_sha256'],
   'raw_manifest_sha256':sha(base/RAW/'manifest.json'),'reviewed_manifest_sha256':sha(base/PROOFS/'reviewed-manifest.json'),
   'proof_projection_summary_sha256':x['projection_summary_sha256'],'target_sha256':sha(base/TARGET),
   'old_source_summary_sha256':sha(base/OLD_SOURCE/'summary.json'),'financial_artifact_sha256':plan['financial_artifact_sha256'],
   'artifact_sha256':{n:sha(out/n) for n in ARTIFACTS},'coverage_scopes_passed':['original151_pre2026','all203_2026_with_Dec31_boundary'],
   'all_unverified_tax_event_keys':sorted(r['instrument']+'|'+r['ex_date'] for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']),
   'original_event_and_receipt_files_copied_byte_exact':True,'all_original_bound_files_unchanged':True,
   'source_queries':0,'account_replay_run':False,'event_compilation_independently_verified':False,'account_replay_admitted':False,
   'actual_zero_record_ownership_verified':False,'fractional_registry_allocation_certified':False,'strict_statutory_tax_certification':False,
   'actual_FIFO_tax_liability_verified':False,'historical_arrival_verified':False,'full_corporate_actions_certified':False,
   'full_October_2026_complete':False,'portfolio_returns_computed':False,'investment_rules_changed':False,'objective_achieved':False}
  with (out/'summary.json').open('x') as f:json.dump(summary,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
 except Exception as error:
  failure={'status':'SOURCE_EVENT_WRITE_FAILED_NOT_ADMITTED','error_type':type(error).__name__,'reason':str(error),'account_replay_admitted':False,'portfolio_returns_computed':False,'source_queries':0}
  with (out/'failure.json').open('x') as f:json.dump(failure,f,indent=2);f.write('\n')
  raise
 print('Source events compiled from authenticated inputs; old378 preserved; independent audit/account admission pending; no ROI')
 return 0


if __name__=='__main__':raise SystemExit(main())
