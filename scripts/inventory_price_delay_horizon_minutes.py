"""Fixed price-delay horizon minute source inventory, never query/replay.
Actual inventory requires the authenticated frozen and pushed request.
"""
import argparse,ast,copy,hashlib,importlib,inspect,json,re,subprocess,sys
from collections import Counter
from datetime import date
from pathlib import Path
START,PRE,END='2023-12-29','2025-12-31','2026-10-20'
TARGET_SHA='5d122dac55da8f57934524de0b6e3640a303363aca49e0a0a09dd70d5850a923'
RAW_AUDIT_SHA='a7bf3324200deb497ba93327fe41c2d4e6ae7fb5b39d7ed81916aaca91ded753'
RAW_MANIFEST_SHA='9fe3990c0b4b1c076b78c97971ceecf593687b2f15699154c3bdbbce666f6490'
# Proposal fixed before inventory: old price-delay prefix authoritative; new day
# precedence uses already registered roots only, independent of quality/returns.
ROOTS=('price-delay-minutes-dev-20261021','low-beta60-minutes-2026-20261021',
 'szse-value-momentum-minutes-dev-20261021','tdx-fixed-order-history-20261017',
 'intraday-prefix-tape-20261017','return-family-minutes-dev-20261017',
 'reversal-minutes-full-20261017','szse-value-minutes-dev-20261017',
 'szse-value-minutes-full-20261017','illiquidity-minutes-dev-20261021',
 'low-beta60-minutes-dev-20261021')
RAW='price-delay-raw-horizon-v2-20261021';FORM='price-delay-horizon-formations-20261021'
OLDRAW='price-delay-raw-dev-20261021';OLDTARGET='price-delay-pre2026-formations-20261021/targets.json'
OLDINV='price-delay-minute-inventory-20261021';OLDCAP=ROOTS[0]
OLDADMIT='price-delay-minute-admission-20261021';OLDSCOPE='price-delay-ordinary-source-scope-20261021'
OUTPUT='price-delay-horizon-minute-inventory-20261021'
METHOD_FILES=('scripts/inventory_price_delay_minutes_pre2026.py','scripts/capture_price_delay_minutes_pre2026.py',
 'scripts/admit_price_delay_minutes_pre2026.py','scripts/illiquidity_minute_sources.py',
 'scripts/capture_low_beta60_minutes_pre2026.py','scripts/admit_low_beta60_minutes_pre2026.py',
 'scripts/fundamental_query_journal.py','scripts/tdx_history_checks.py',
 'src/stock_rsi/intraday_tape.py','src/stock_rsi/lifecycle_source_rows.py',
 'src/stock_rsi/data.py','src/stock_rsi/calendar.py','src/stock_rsi/time.py',
 'scripts/prepare_price_delay_horizon_formations.py')
PUBLIC_FILES=('experiments/qlib/price-delay-horizon-local-reassembly-independent-audit.json',
 'experiments/qlib/price-delay-horizon-formation-independent-audit.json',
 'experiments/qlib/price-delay-minute-capture-independent-audit.json',
 'experiments/qlib/price-delay-minute-admission-independent-audit.json',
 'experiments/qlib/price-delay-ordinary-source-scope-independent-audit.json',
 'experiments/qlib/price-delay-minute-capture-plan.json',
 'experiments/qlib/price-delay-minute-gap-identities.json',
 'experiments/qlib/price-delay-horizon-raw-source-request.json')
LOCAL_FILES=(RAW+'/manifest.json',RAW+'/calendar.json',FORM+'/candidate_targets.json',FORM+'/summary.json',
 OLDRAW+'/manifest.json',OLDRAW+'/calendar.json',OLDTARGET,OLDINV+'/details.json',
 OLDCAP+'/manifest.json',OLDCAP+'/price-delay-scope.json',OLDCAP+'/plan.json',OLDCAP+'/request.json',
 OLDCAP+'/capture_request.json',OLDCAP+'/client_cleanup.json',OLDADMIT+'/summary.json',OLDADMIT+'/details.json',
 OLDSCOPE+'/summary.json',OLDSCOPE+'/scope.json')
def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def require(ok,message):
 if not ok:raise ValueError(message)
def safe(root,name):
 p=Path(root)/name;require(not Path(name).is_absolute() and '..' not in Path(name).parts and p.resolve().is_relative_to(Path(root).resolve()),'safe relative source path required');return p
def valid_pair(code,day):
 try:ok=isinstance(code,str) and re.fullmatch('(SH|SZ)[0-9]{6}',code) and isinstance(day,str) and date.fromisoformat(day).isoformat()==day and '2024-01-02'<=day<=END
 except (TypeError,ValueError):ok=False
 require(ok,'canonical source-window minute identity required')
def clone_functions(prefix_function,inspect_function):
 """Only one source-date cap changes; ordinary tape tests/body stay identical."""
 original=ast.parse(inspect.getsource(prefix_function));transformed=copy.deepcopy(original);changed=0
 for node in ast.walk(transformed):
  if isinstance(node,ast.Constant) and node.value=='2025-12-31':node.value=END;changed+=1
 require(changed==1,'exact one old date-cap literal required')
 def build(tree,namespace,name):
  ns=dict(namespace);exec(compile(ast.fix_missing_locations(tree),'<frozen-source-date-adapter>','exec'),ns);return ns[name]
 prefix=build(transformed,prefix_function.__globals__,prefix_function.__name__)
 tape_ast=ast.parse(inspect.getsource(inspect_function));namespace=dict(inspect_function.__globals__);namespace['valid_pair']=valid_pair
 tape=build(tape_ast,namespace,inspect_function.__name__)
 return prefix,tape,{'prefix_original_AST_sha256':digest(ast.dump(original,include_attributes=False)),
  'prefix_extended_AST_sha256':digest(ast.dump(transformed,include_attributes=False)),
  'date_cap_literals_changed':changed,'inspect_function_AST_unchanged':True,
  'original_cap':'2025-12-31','extended_source_cap':END}
def load_adapters(repo):
 sys.path.insert(0,str(repo));sys.path.insert(0,str(Path(repo)/'src'))
 a=importlib.import_module('scripts.illiquidity_minute_sources');b=importlib.import_module('scripts.admit_low_beta60_minutes_pre2026')
 return clone_functions(a.prefix_minute_requirements,b.inspect_packet)
def validate_prefix(sessions,old_sessions,targets,old_targets,*,full=True):
 require(sessions==sorted(set(sessions)) and sessions[:len(old_sessions)]==old_sessions,'explicit calendar prefix changed')
 require(list(sorted(targets.items()))[:len(old_targets)]==list(sorted(old_targets.items())),'literal old target object prefix changed')
 for day,target in sorted(targets.items()):
  valid_pair('SH600000',day);require(day in sessions and sessions.index(day)>0 and target['as_of']==sessions[sessions.index(day)-1],'prior-close source session identity changed')
 if full:require(len(sessions)==676 and len(old_sessions)==486 and sessions[0]==START and sessions[-1]==END and len(targets)==34 and len(old_targets)==24,'fixed676/486/34/24 required')
def source_state(daily):
 if daily.get('isST')=='0':return 'ORDINARY_FLAG_ZERO'
 if daily.get('isST')=='1':return 'NONORDINARY_FLAG_ONE'
 return 'ORDINARY_FLAG_UNKNOWN'
def cache_pair(code,day,daily,origins,load_packet,inspect_tape):
 """Hash/metadata and all-reference conflict check; never choose by quality."""
 valid_pair(code,day);state=source_state(daily)
 if not origins:return {'status':'MISSING_CACHED_PACKET','source_state':state,'origins':[]}
 signatures=set();errors=[];packets=[];source_records=[]
 for origin in origins:
  packet=load_packet(origin);require(packet['instrument']==code and packet['requested_day']==day,'cached issuer/day mismatch')
  rec=packet.get('methods',{}).get('minutes.history',packet);require(rec.get('status') in ('RESPONSE_CAPTURED','REQUEST_FAILED'),'cached source status changed')
  signatures.add(digest({'status':rec['status'],'response':rec.get('response')}));packets.append(packet);source_records.append({'root':origin['root'],'sha256':origin['sha256'],'source_status':rec['status']})
  if rec['status']!='RESPONSE_CAPTURED':errors.append({'root':origin['root'],'error_type':'SOURCE_UNAVAILABLE','reason':'retained original source failure; no implicit retry'})
  if state=='ORDINARY_FLAG_ZERO':
   try:inspect_tape(code,day,packet,daily)
   except (ValueError,KeyError,TypeError,ArithmeticError) as exc:errors.append({'root':origin['root'],'error_type':type(exc).__name__,'reason':str(exc)})
 status='CONFLICTING_CACHED_RESPONSES' if len(signatures)!=1 else 'INVALID_ORDINARY_CACHED_PACKET' if errors else 'CACHED_SOURCE_PACKET_RETAINED'
 return {'status':status,'source_state':state,'origins':origins,'source_records':source_records,'distinct_response_signatures':len(signatures),'ordinary_inspection_errors':errors,'selected_origin':origins[0] if status=='CACHED_SOURCE_PACKET_RETAINED' else None,'ordinary_source_quality_checked':state=='ORDINARY_FLAG_ZERO','source_or_account_admitted':False}
def inventory_new_pairs(active,bars,index,load_packet,inspect_tape):
 result={};missing=[];reused={};invalid=[];conflict=[];nonordinary=[]
 for c,d in active:
  name=c+'-'+d+'.json';row=cache_pair(c,d,bars[c][d],index.get(name,[]),lambda origin:load_packet(origin,name),inspect_tape);result[name]=row
  if row['source_state']!='ORDINARY_FLAG_ZERO':nonordinary.append({'instrument':c,'day':d,'source_state':row['source_state'],'required_account_dependency_proof':True,'actual_inventory_proven_zero':False})
  if row['status']=='MISSING_CACHED_PACKET':missing.append([c,d])
  elif row['status']=='CONFLICTING_CACHED_RESPONSES':conflict.append([c,d])
  elif row['status']=='INVALID_ORDINARY_CACHED_PACKET':invalid.append([c,d])
  else:reused[name]=row['selected_origin']
 return {'cached_reference_details':result,'reused_session_provenance':reused,'uncached_requests':missing,'invalid_cached_requests':invalid,'conflicting_cached_requests':conflict,'nonordinary_or_unknown_source_markers':nonordinary,'proposed_maximum_new_logical_queries':len(missing),'new_network_queries':0,'account_dependency_proven':False}
def authenticate_old_evidence(base,repo,old_active,old_skipped,bars):
 cm=read(base/OLDCAP/'manifest.json');am=read(base/OLDADMIT/'summary.json');details=read(base/OLDADMIT/'details.json');scope=read(base/OLDSCOPE/'scope.json');ss=read(base/OLDSCOPE/'summary.json')
 ca=read(repo/PUBLIC_FILES[2]);aa=read(repo/PUBLIC_FILES[3]);oa=read(repo/PUBLIC_FILES[4])
 require(sha(repo/PUBLIC_FILES[5])==ca['capture_plan_sha256']==sha(base/OLDCAP/'plan.json') and sha(repo/PUBLIC_FILES[6])==ca['request_sha256']==sha(base/OLDCAP/'request.json') and ca['scope_sha256']==sha(base/OLDCAP/'price-delay-scope.json') and cm['capture_request_sha256']==sha(base/OLDCAP/'capture_request.json'),'old canonical plan/request/scope/partition')
 snapshot=base/OLDCAP/('capture-snapshot-'+digest(cm)+'.json');require(sha(snapshot)==ca['legacy_snapshot_sha256'] and read(snapshot)==cm,'old immutable capture snapshot')
 require(ca['capture_manifest_sha256']==sha(base/OLDCAP/'manifest.json') and ca['capture_fully_recorded'] is True and ca['imports_project_code'] is False,'old independent capture binding')
 require(aa['admission_summary_sha256']==sha(base/OLDADMIT/'summary.json') and aa['admission_details_sha256']==sha(base/OLDADMIT/'details.json') and aa['failed_admission_correctly_preserved'] is True and aa['all2502_details_and_entire_summary_reconstructed'] is True and aa['imports_project_code'] is False,'old failed admission anchor')
 require(oa['source_scope_sha256']==sha(base/OLDSCOPE/'scope.json') and oa['source_summary_sha256']==sha(base/OLDSCOPE/'summary.json') and oa['ordinary_scope_reconstructed'] is True and oa['imports_project_code'] is False,'old ordinary scope anchor')
 require(am['admitted_for_reconstructed_execution'] is False and am['status_counts']=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':2490,'SOURCE_REJECTED':12} and ss['original_strict_admission_remains_failed'] is True,'failed admission remains false')
 require(len(old_active)==2502 and len(old_skipped)==2 and details['nonexecuting_source_intervals']==old_skipped and [[r['instrument'],r['day']] for r in details['sessions']]==old_active,'exact old2502/2 identities')
 require(len(cm['per_session_sha256'])==2502 and set(cm['per_session_sha256'])=={c+'-'+d+'.json' for c,d in old_active},'old2502 packet scope')
 require(len(scope['ordinary_packet_sha256'])==2490 and len(scope['rejected_packet_sha256'])==12 and {**scope['ordinary_packet_sha256'],**scope['rejected_packet_sha256']}==cm['per_session_sha256'],'2490ordinary+12retained exactsourcehashes')
 for name,h in cm['per_session_sha256'].items():require(sha(base/OLDCAP/'sessions'/name)==h,'old minute bytes changed')
 q={str(p.relative_to(base/OLDCAP)):sha(p) for p in (base/OLDCAP/'queries').rglob('*') if p.is_file()};require(q==ca['query_artifact_sha256']==aa['query_artifact_sha256'],'old exact journal filetree')
 rejected=[r for r in details['sessions'] if r['status']=='SOURCE_REJECTED'];require(len(rejected)==12 and all(bars[r['instrument']][r['day']]['isST']=='1' and bars[r['instrument']][r['day']]['tradestatus']=='1' for r in rejected),'retain12 ordinary-rule ST rejections')
 return {'original2502_packet_sha256':cm['per_session_sha256'],'ordinary2490_packet_sha256':scope['ordinary_packet_sha256'],'rejected12_packet_sha256':scope['rejected_packet_sha256'],'original_failed_admission_summary_sha256':sha(base/OLDADMIT/'summary.json'),'original_failed_admission_details_sha256':sha(base/OLDADMIT/'details.json'),'original_failed_admission_remains_false':True,'ordinary_source_scope_sha256':sha(base/OLDSCOPE/'scope.json'),'old_query_artifact_sha256':q,'original_nonexecuting_source_intervals':old_skipped,'retained_rejected_details':rejected,'original_nonordinary_intervals':scope['nonordinary_source_intervals'],'new_account_dependency_proof_granted':False}
def verify_financial_prefix(plan,base,repo):
 from scripts.prepare_price_delay_horizon_formations import immutable_financial_hashes
 original=read(repo/'experiments/qlib/price-delay-horizon-raw-source-request.json')['immutable_financial_sha256']
 require(len(original)==48 and plan['immutable_financial_sha256']==original and immutable_financial_hashes(base)==original,'exact original48 financial artifacts must remain unchanged')
 for name,h in original.items():require(sha(safe(base,name))==h,'original financial file bytes changed: '+name)

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','repo-root','plan','expected-plan-sha256','output-dir','frozen-commit'):p.add_argument('--'+n,required=True)
 p.add_argument('--execute-frozen-inventory',action='store_true');a=p.parse_args(argv)
 require(a.execute_frozen_inventory,'external review/freeze/push before actual inventory required');require(sha(a.plan)==a.expected_plan_sha256,'external frozen plan SHA changed')
 base,repo,out=Path(a.source_root),Path(a.repo_root),Path(a.output_dir);plan=read(a.plan)
 verify_financial_prefix(plan,base,repo)
 require(not out.exists() and out.resolve()==(base/OUTPUT).resolve(),'fixed unused output required')
 freeze=subprocess.check_output(['git','rev-parse',a.frozen_commit],cwd=repo,text=True).strip()
 require(Path(a.plan).resolve().is_relative_to(repo.resolve()) and sha(a.plan)==hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(Path(a.plan).resolve().relative_to(repo.resolve()))],cwd=repo)).hexdigest(),'frozen committed plan bytes required')
 require(sha(safe(repo,plan['script_file']))==plan['script_sha256']==hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+plan['script_file']],cwd=repo)).hexdigest(),'frozen committed adapter required')
 require(plan['status']=='FROZEN_PRICE_DELAY_HORIZON_MINUTE_SOURCE_INVENTORY' and plan['candidate']=='price_delay_d1' and plan['source_precedence']==list(ROOTS) and type(plan['maximum_network_queries']) is int and plan['maximum_network_queries']==0 and plan['portfolio_returns_computed'] is False and plan['script_sha256']==sha(Path(__file__)),'fixed source-only profile')
 for field,names,parent in [('method_code_sha256',METHOD_FILES,repo),('public_evidence_sha256',PUBLIC_FILES,repo),('local_source_sha256',LOCAL_FILES,base)]:
  require(set(plan[field])==set(names),'complete exact binding scope '+field)
  for n,h in plan[field].items():
   require(sha(safe(parent,n))==h,'frozen source/method/evidence changed '+n)
   if parent==repo:require(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=repo)).hexdigest()==h,'frozen committed method/evidence required '+n)
 require(set(plan['source_manifest_sha256'])==set(ROOTS),'all cache manifests required')
 for n,h in plan['source_manifest_sha256'].items():require(sha(base/n/'manifest.json')==h,'cached manifest changed')
 require(sha(base/RAW/'manifest.json')==RAW_MANIFEST_SHA and sha(repo/PUBLIC_FILES[0])==RAW_AUDIT_SHA and sha(base/FORM/'candidate_targets.json')==TARGET_SHA,'known independent raw/target anchors')
 rm=read(base/RAW/'manifest.json');ra=read(repo/PUBLIC_FILES[0]);require(ra['manifest_sha256']==RAW_MANIFEST_SHA and ra['all203_packets_676_sessions_verified'] is True and ra['imports_project_code'] is False and ra['all151_original_literal_pre2026_prefixes_identical'] is True and rm['source_admitted_for_account_replay'] is False and rm['names']==203,'raw203sourceonly audit')
 sessions=read(base/RAW/'calendar.json')['sessions'];old_sessions=read(base/OLDRAW/'calendar.json')['sessions'];targets=read(base/FORM/'candidate_targets.json');old_targets=read(base/OLDTARGET)['price_delay_d1'];validate_prefix(sessions,old_sessions,targets,old_targets)
 bars={}
 for c,h in rm['per_code_sha256'].items():
  f=base/RAW/'codes'/(c+'.json');require(sha(f)==h,'rawpacket bytes changed');v=read(f);require(v['instrument']==c and v['window']==[START,END] and [r['date'] for r in v['bars']]==sessions,'complete raw sourcecalendar');bars[c]={r['date']:r for r in v['bars']}
 require({c for t in targets.values() for c in t['weights']}==set(bars),'fixed203 source universe')
 prefix,inspect_tape,adapter=load_adapters(repo);active,skipped=prefix(targets,bars,{})
 old_active=[x for x in active if x[1]<=PRE];old_skipped=[x for x in skipped if x['day']<=PRE];oldinv=read(base/OLDINV/'details.json')
 require(old_active==oldinv['active_requests'] and old_skipped==oldinv['nonexecuting_source_intervals'],'old generation2502 prefix changed');old=authenticate_old_evidence(base,repo,old_active,old_skipped,bars)
 new_active=[x for x in active if x[1]>PRE];new_skipped=[x for x in skipped if x['day']>PRE];index={}
 for name in ROOTS:
  for filename,h in read(base/name/'manifest.json')['per_session_sha256'].items():
   require(Path(filename).name==filename and filename.endswith('.json'),'safe cached filename');index.setdefault(filename,[]).append({'root':name,'sha256':h})
 def load_packet(origin,name):
  f=base/origin['root']/'sessions'/name;require(sha(f)==origin['sha256'],'cached packet bytes changed');return read(f)
 part=inventory_new_pairs(new_active,bars,index,load_packet,inspect_tape)
 detail={'candidate':'price_delay_d1','source_precedence':list(ROOTS),'source_manifest_sha256':plan['source_manifest_sha256'],'raw_manifest_sha256':RAW_MANIFEST_SHA,'target_sha256':TARGET_SHA,'all_active_requests':active,'new2026_active_requests':new_active,'all_nonexecuting_source_intervals':skipped,'new2026_nonexecuting_source_intervals':new_skipped,'old_pre2026_evidence':old,'date_cap_adapter':adapter,**part}
 # Rehash every bound input and referenced packet before writing completion.
 for field,parent in [('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)]:
  for n,h in plan[field].items():require(sha(parent/n)==h,'postcheck input changed')
 for root,h in plan['source_manifest_sha256'].items():require(sha(base/root/'manifest.json')==h,'postcheck cachemanifest changed')
 for c,h in rm['per_code_sha256'].items():require(sha(base/RAW/'codes'/(c+'.json'))==h,'postcheck rawpacket changed')
 for filename,h in old['original2502_packet_sha256'].items():require(sha(base/OLDCAP/'sessions'/filename)==h,'postcheck oldminute changed')
 for filename,row in part['cached_reference_details'].items():
  for origin in row['origins']:require(sha(base/origin['root']/'sessions'/filename)==origin['sha256'],'postcheck cachedpacket changed')
 verify_financial_prefix(plan,base,repo)
 out.mkdir(parents=True);(out/'details.json').write_text(json.dumps(detail,ensure_ascii=False,indent=2)+'\n')
 summary={'status':'PRICE_DELAY_HORIZON_MINUTE_INVENTORY_NOT_ADMISSION','candidate':'price_delay_d1','plan_sha256':a.expected_plan_sha256,'freeze_commit':freeze,'script_sha256':sha(Path(__file__)),'method_code_sha256':plan['method_code_sha256'],'source_precedence_fixed_before_inventory':list(ROOTS),'raw_manifest_sha256':RAW_MANIFEST_SHA,'target_sha256':TARGET_SHA,'source_calendar_sessions':676,'original486_calendar_prefix_identical':True,'original24_target_object_prefix_identical':True,'original_pre2026_required_pairs':2502,'original_ordinary_admitted_evidence':2490,'original_ST_rejected_evidence_retained':12,'original_failed_admission_remains_false':True,'new2026_active_pairs':len(new_active),'new2026_nonexecuting_intervals':len(new_skipped),'new2026_cached_reuse_pairs':len(part['reused_session_provenance']),'new2026_missing_pairs':len(part['uncached_requests']),'new2026_invalid_cached_pairs':len(part['invalid_cached_requests']),'new2026_conflicting_cached_pairs':len(part['conflicting_cached_requests']),'new2026_nonordinary_or_unknown_markers':len(part['nonordinary_or_unknown_source_markers']),'proposed_maximum_new_logical_queries':part['proposed_maximum_new_logical_queries'],'inventory_network_queries':0,'all48_original_financial_artifacts_unchanged':True,'new2026_cached_minute_values_read':any(row['origins'] for row in part['cached_reference_details'].values()),'minute_values_used_for_target_or_rule_selection':False,'details_sha256':sha(out/'details.json'),'capture_authorized':False,'account_dependency_guard_required':True,'all_account_dependencies_ordinary_proven':False,'source_admitted_for_account_replay':False,'portfolio_returns_computed':False,'full_October_2026_complete':False,'historical_arrival_verified':False,'objective_achieved':False}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k.startswith('new2026_') or k=='proposed_maximum_new_logical_queries'}));return 0
if __name__=='__main__':raise SystemExit(main())
