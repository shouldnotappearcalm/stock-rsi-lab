"""Independent stdlib-only audit of one fixed pre2026 monthly risk target trial.
No project imports, account/portfolio replay, account-output JSON/CSV decoding,
Parquet decoder, network, ranking search or future-price interface is used.
Run --self-test alone for synthetic fixtures; actual main needs frozen inputs.
"""
import argparse,copy,hashlib,json,math,re,struct,sys,tempfile
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace
LOCAL=timezone(timedelta(hours=8))
UTC=timezone.utc
CONTRACT='BINARY32_UNIQUE_CENT_CLOCK_INTERSECTION_V1'
RAW='illiquidity-raw-source-continuation-20261020'
PROOF='illiquidity-corporate-reviewed-20261020'
EVENTS='illiquidity-source-events-20261020'
TARGET='illiquidity-development-targets-20261020.json'
OLD='tdx-fixed-order-history-20261017'
EXTRA='illiquidity-minutes-dev-20261021'
ARCHIVE='illiquidity-hf-archive-probe-20261021'
GRID='illiquidity-archive-cent-grid-primary-20261022'
DETAIL='illiquidity-minute-admission-20261021-v2/details.json'
PUBLIC='experiments/qlib/'
MINREQ=PUBLIC+'illiquidity-minute-development-request.json'
ADMISSION=PUBLIC+'illiquidity-development-minute-admission.json'
VERIFY=PUBLIC+'illiquidity-hf-archive-probe-run-verification.json'
PUBLIC_FILES=(MINREQ,ADMISSION,VERIFY,*[PUBLIC+n for n in ('illiquidity-minute-development-capture-plan.json','illiquidity-minute-development-capture-manifest.json','illiquidity-raw-source-capture-manifest.json','illiquidity-corporate-reviewed-manifest.json','illiquidity-corporate-capture-manifest.json','illiquidity-source-event-compilation.json','illiquidity-hf-archive-probe-request.json','illiquidity-hf-archive-probe-independent-audit.json','illiquidity-hf-archive-probe-results.json','illiquidity-hf-archive-probe-final-review.json','illiquidity-hf-archive-metadata-discovery.json','illiquidity-archive-cent-clock-code-review.json','illiquidity-archive-cent-grid-primary-research.json','illiquidity-archive-scenario-builder-code-review.json')])
METHODS=set('''scripts/prepare_illiquidity_account_events.py
src/stock_rsi/distribution_event_compiler.py
src/stock_rsi/lifecycle_source_rows.py
src/stock_rsi/stock_distribution_account.py
scripts/run_low_risk_raw_share_validation.py
scripts/capture_frozen_target_development_data.py
src/stock_rsi/raw_share_account.py
src/stock_rsi/calendar.py
src/stock_rsi/broker.py
src/stock_rsi/data.py
src/stock_rsi/time.py
scripts/run_low_risk_intraday_replay.py
scripts/capture_cninfo_csi500_reports_pre2026.py
scripts/capture_low_risk_raw_account_data.py
scripts/tdx_history_checks.py
src/stock_rsi/intraday_broker.py
src/stock_rsi/intraday_tape.py
src/stock_rsi/execution_cost.py
src/stock_rsi/models.py
scripts/admit_illiquidity_minutes_pre2026.py
scripts/illiquidity_minute_sources.py
scripts/fundamental_query_journal.py
scripts/prepare_qlib_master_market_pre2026.py
scripts/build_illiquidity_archive_scenario_sources.py
src/stock_rsi/archive_cent_clock.py
src/stock_rsi/archive_minute_probe.py'''.splitlines())

def need(v,label):
 if not v:raise AssertionError(label)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def read(p):return json.loads(Path(p).read_bytes())

def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()

def verify_sha(path,expected):need(sha(path)==expected,'actual source SHA256 differs from frozen binding')

def negative(fn):
 try:fn()
 except (AssertionError,ValueError,KeyError,OverflowError):return True
 raise AssertionError('synthetic negative accepted')

def required_inputs(base,repo):
 paths={}
 def add(path):
  p=Path(path).resolve()
  if p.is_relative_to(repo):key='repo/'+str(p.relative_to(repo))
  else:need(p.is_relative_to(base),'registered input escapes frozen roots');key='source/'+str(p.relative_to(base))
  paths[key]=p
 for name in set(PUBLIC_FILES)|METHODS:add(repo/name)
 for folder,name in [(RAW,'manifest.json'),(PROOF,'reviewed-manifest.json'),(EVENTS,'summary.json'),(OLD,'manifest.json'),(EXTRA,'manifest.json')]:add(base/folder/name)
 for name in [TARGET,DETAIL,RAW+'/calendar.json',PROOF+'/capture-manifest.json',OLD+'/plan.json',EXTRA+'/plan.json',GRID+'/manifest.json']:add(base/name)
 for code in read(base/RAW/'manifest.json')['per_code_sha256']:
  need(re.fullmatch(r'(SH|SZ)[0-9]{6}',code) is not None,'safe original source issuer');add(base/RAW/'codes'/(code+'.json'))
 for doc in read(base/PROOF/'reviewed-manifest.json')['documents']:need(Path(doc['file']).name==doc['file'],'safe primary filename');add(base/PROOF/doc['file'])
 for name in read(base/EVENTS/'summary.json')['artifact_sha256']:need(Path(name).name==name,'safe event artifact filename');add(base/EVENTS/name)
 index={}
 for folder in (OLD,EXTRA):
  for name in read(base/folder/'manifest.json')['per_session_sha256']:
   need(Path(name).name==name and name.endswith('.json') and name not in index,'safe unique original tape filename');index[name]=base/folder/'sessions'/name
 for code,day in read(repo/MINREQ)['active_requests']:
  need('2024-01-01'<=day<='2025-12-31','pre2026 tape scope');add(index[code+'-'+day+'.json'])
 for name in read(repo/VERIFY)['all13_local_output_file_sha256']:need(Path(name).name==name,'safe archive output filename');add(base/ARCHIVE/name)
 for path in read(base/ARCHIVE/'input-before.json'):add(path)
 for path in (base/GRID).iterdir():
  if path.is_file():add(path)
 return paths

def scope_from_targets(targets,bars,lifecycles):
 active=[];skipped=[];seen=set()
 for day,target in sorted(targets.items()):
  need('2024-01-02'<=day<='2025-12-31' and target['as_of']<day,'fixed pre2026 target clock');seen.update(target['weights']);need(seen<=set(bars),'complete source universe')
  for code in sorted(seen):
   boundary=lifecycles.get(code,{});row=bars[code].get(day);kind=boundary.get('kind');outside=(kind=='LISTING_BEGIN' and day<boundary['effective_date']) or (kind=='DELISTING_END' and day>=boundary['effective_date'])
   if outside:
    need(code not in target['weights'],'current target cannot use outside lifecycle source');need(boundary['verified_primary_boundary'] is True and re.fullmatch('[0-9a-f]{64}',boundary['primary_document_sha256']) is not None,'authenticated original lifecycle proof')
    if kind=='LISTING_BEGIN':need(row is None,'no source row before original listing boundary')
    reason='BEFORE_PRIMARY_LISTING_BOUNDARY' if kind=='LISTING_BEGIN' else 'AT_OR_AFTER_PRIMARY_DELISTING_BOUNDARY'
    skipped.append({'instrument':code,'day':day,'reason':reason,'primary_document_sha256':boundary['primary_document_sha256'],'actual_inventory_proven_zero':False,'synthetic_price_created':False})
   else:
    need(row is not None and row['date']==day,'unexplained source missing day')
    if row['tradestatus']=='0':skipped.append({'instrument':code,'day':day,'reason':'SOURCE_HALT','actual_inventory_proven_zero':False,'synthetic_price_created':False})
    else:need(row['tradestatus']=='1','known raw source status');active.append([code,day])
 return active,skipped
SOURCE_DIR='illiquidity-archive-scenario-sources-20261022'
SOURCE_REQUEST=PUBLIC+'illiquidity-archive-scenario-source-request.json'
SOURCE_REQUEST_SHA='c917b4c4cde4a6ce13d626e0ccc8f1f80f6875c08b417e07d98b29c6ba4a191c'
SOURCE_AUDIT=PUBLIC+'illiquidity-archive-scenario-independent-source-audit.json'
SOURCE_VERIFY=PUBLIC+'illiquidity-archive-scenario-source-run-verification.json'
LEDGER_AUDIT=PUBLIC+'audit_sources/2026-10-22-illiquidity-source-scenario-development-ledger.py'
ACCOUNT_METHODS=METHODS|{'scripts/run_illiquidity_intraday_development.py','scripts/replay_stock_distribution_targets.py','scripts/illiquidity_scenario_tape.py','scripts/run_illiquidity_source_scenario_development.py'}
ACCOUNT_PUBLIC=(SOURCE_REQUEST,SOURCE_AUDIT,SOURCE_VERIFY,PUBLIC+'illiquidity-archive-scenario-source-results.json',PUBLIC+'audit_sources/2026-10-22-illiquidity-archive-scenario-independent-source-audit.py',PUBLIC+'illiquidity-pre2026-results.json',PUBLIC+'illiquidity-pre2026-independent-csv-audit.json',PUBLIC+'illiquidity-pre2026-plan.json',PUBLIC+'illiquidity-scenario-tape-code-review.json',PUBLIC+'illiquidity-source-scenario-development-code-review.json',LEDGER_AUDIT,'docs/research/illiquidity-source-scenario-development-contract-2026-10-22.md')
PARTICIPATIONS=(100,500,1000)
COSTS=(0,5,10,20,40)
CAPITALS=('100000','1000000','10000000','100000000')

def required_account_inputs(base,repo):
 paths=required_inputs(base,repo)
 for name in ACCOUNT_METHODS|set(ACCOUNT_PUBLIC):paths['repo/'+name]=repo/name
 outputs=read(repo/SOURCE_VERIFY)['all34_output_file_sha256'];need(len(outputs)==34,'exact independently verified source34 map')
 for name in outputs:need(Path(name).name==name,'safe source output filename');paths['source/'+SOURCE_DIR+'/'+name]=base/SOURCE_DIR/name
 return paths
RISK_POLICY='amihud22_monthly_price_risk1'
RISK_CONTRACT='MONTHLY_RAW_CLOSE_1CNY_ORDINARY_GUARD_V1'
RISK_TARGET_DIR='amihud-monthly-price-risk-targets-20261022'
RISK_PRIMARY_DIR='amihud-monthly-price-risk-primary-20261022'
RISK_METHOD='src/stock_rsi/monthly_price_risk.py'
RISK_BUILDER='scripts/build_monthly_price_risk_targets.py'
RISK_RUNNER='scripts/run_monthly_price_risk_development.py'
RISK_LEDGER_AUDIT=PUBLIC+'audit_sources/2026-10-22-amihud-monthly-price-risk-development-ledger.py'
RISK_QUANTUM=10**24

def independent_numeric(value):
 need(type(value) in (str,int,float),'finite explicit original JSON numeric value, no bool')
 try:result=D(str(value))
 except Exception:raise AssertionError('invalid decimal formation field')
 need(result.is_finite(),'no nonfinite formation price/weight');return result

def independent_risk_target(seed,cells):
 """Source-only monthly policy, independently using integer/Fraction weights.

 Exact Fraction arithmetic determines the 24-place downward proportions;
 cent-grid validation is explicit rather than binary floating tolerances.
 No ticker identity, future row, outcome, execution or statutory-day count.
 """
 need(type(seed) is dict and set(seed)=={'as_of','weights'} and type(seed['weights']) is dict and seed['weights'],'nonempty original seed target schema')
 asof=seed['as_of'];need(type(asof) is str and date.fromisoformat(asof).isoformat()==asof and '2023-12-29'<=asof<='2025-12-31','canonical capped formation date')
 weights={c:independent_numeric(v) for c,v in seed['weights'].items()};need(all(w>0 for w in weights.values()) and abs(sum(weights.values())-D('.95'))<=D('1e-12'),'original positive95percent seed total')
 need(type(cells) is dict and set(cells)==set(weights),'only exact seed-selected formation cells')
 blocked={}
 for code in sorted(weights):
  row=cells[code];need(type(row) is dict and set(row)=={'date','close','tradestatus','isST'} and row['date']==asof,'exact four-field current formation cell; no future/extra fields')
  need(row['tradestatus'] in ('0','1') and row['isST'] in ('0','1'),'known source activity/ST state')
  reasons=[]
  if row['tradestatus']=='0':reasons.append('KNOWN_FORMATION_HALT')
  else:
   close=independent_numeric(row['close']);need(close>0 and close.adjusted()<=25 and F(close)*100==int(F(close)*100),'positive active exact cent price')
   if close<D('1.00'):reasons.append('FORMATION_RAW_CLOSE_BELOW_CNY1')
  if row['isST']=='1':reasons.append('KNOWN_FORMATION_ST_STATE')
  if reasons:blocked[code]=reasons
 retained=sorted(set(weights)-set(blocked))
 if not blocked:result=copy.deepcopy(seed['weights'])
 elif not retained:result={c:'0' for c in sorted(weights)}
 elif len(retained)==1:result={retained[0]:'0.95'}
 else:
  # Source module sums fixed JSON Decimal weights before its high-precision
  # division. Preserve that exact total; do not silently renormalize seed sum.
  total=F(sum(weights[c] for c in retained));units={}
  for code in retained[:-1]:
   ratio=F(95,100)*F(weights[code])*RISK_QUANTUM/total;units[code]=ratio.numerator//ratio.denominator
  units[retained[-1]]=95*10**22-sum(units.values());need(all(q>0 for q in units.values()) and sum(units.values())==95*10**22,'exact95percent positive residual allocation')
  result={c:str(q//RISK_QUANTUM)+'.'+str(q%RISK_QUANTUM).zfill(24) for c,q in units.items()}
 evidence={'contract':RISK_CONTRACT,'formation_asof':asof,'original_seed_target':copy.deepcopy(seed),'formation_cells':copy.deepcopy(cells),'minimum_raw_close_CNY':'1.00','blocked':blocked,'retained':retained};eid=digest(evidence)
 target={'as_of':asof,'weights':result,'risk_overlay':{'contract':RISK_CONTRACT,'formation_evidence_id':eid}}
 receipt={**evidence,'formation_evidence_id':eid,'result_weights':copy.deepcopy(result),'all_filtered_to_cash':not retained,'statutory_delisting_classifier':False,'historical_arrival_verified':False}
 return target,receipt

def independent_risk_formations(seeds,sessions,reader):
 need(type(sessions) is list and sessions==sorted(set(sessions)),'explicit unique source calendar');targets={};receipts=[];accesses=[]
 for execution,seed in sorted(seeds.items()):
  need('2024-01-02'<=execution<='2025-12-31' and execution in sessions,'fixed pre2026 execution clock before provider access');i=sessions.index(execution);need(i>0 and seed['as_of']==sessions[i-1],'immediate prior observed source session')
  ex=date.fromisoformat(execution);formation=date.fromisoformat(seed['as_of']);previous=(ex.year,ex.month-1) if ex.month>1 else (ex.year-1,12);need((formation.year,formation.month)==previous,'formation lies in immediately previous calendar month')
  cells={}
  for code in sorted(seed['weights']):accesses.append([code,seed['as_of']]);cells[code]=reader(code,seed['as_of'])
  target,receipt=independent_risk_target(seed,cells);targets[execution]=target;receipts.append({'execution_session':execution,**receipt})
 return targets,receipts,accesses

def check_risk_target_output_objects(seeds,sessions,reader,targets,receipts,accesses):
 expected_targets,expected_receipts,expected_access=independent_risk_formations(seeds,sessions,reader)
 need(targets==expected_targets and receipts==expected_receipts and accesses==expected_access,'all targets, complete receipts/evidence and exact access sequence independently reconstructed')
 need(set(targets)==set(seeds) and len(receipts)==len(seeds),'no skipped/extra formation')
 for day,target in targets.items():need(set(target['weights'])<=set(seeds[day]['weights']),'no added security/rank substitution')
 return {'all_targets_independently_reconstructed':len(targets),'all_receipts_independently_reconstructed':len(receipts),'formation_cell_reads':len(accesses),'changed_weight_months':sum(targets[d]['weights']!=seeds[d]['weights'] for d in targets),'blocked_reason_counts':dict(Counter(reason for r in receipts for reasons in r['blocked'].values() for reason in reasons)),'all_filtered_cash_months':sum(r['all_filtered_to_cash'] for r in receipts),'actual_exit_proven_by_target_generation':False,'statutory_delisting_classifier':False}

def independent_risk_selftests():
 inherited={'negative_controls':{}};seed={'as_of':'2024-04-30','weights':{'A':.475,'B':.475}};cells={c:{'date':seed['as_of'],'close':'1.00','tradestatus':'1','isST':'0'} for c in seed['weights']};before=copy.deepcopy((seed,cells));noop,receipt=independent_risk_target(seed,cells);need(noop['weights']==seed['weights'] and (seed,cells)==before and not receipt['blocked'],'exact no-op/nonmutation at1CNY')
 below=copy.deepcopy(cells);below['B']['close']='.99';filtered,r=independent_risk_target(seed,below);need(filtered['weights']=={'A':'0.95'} and r['blocked']=={'B':['FORMATION_RAW_CLOSE_BELOW_CNY1']},'strict below1 not equal1 cutoff')
 allblocked=copy.deepcopy(cells);allblocked['A'].update(tradestatus='0',close='');allblocked['B']['isST']='1';cash,r=independent_risk_target(seed,allblocked);need(cash['weights']=={'A':'0','B':'0'} and r['all_filtered_to_cash'] and r['blocked']['A']==['KNOWN_FORMATION_HALT'] and r['blocked']['B']==['KNOWN_FORMATION_ST_STATE'],'known halted/ST allblocked names retained aszero cash desires')
 uneven={'as_of':'2024-04-30','weights':{'A':'.2375','B':'.2375','C':'.2375','D':'.2375'}};uc={c:{'date':'2024-04-30','close':'.99' if c=='A' else '10.00','tradestatus':'1','isST':'0'} for c in uneven['weights']};weighted,_=independent_risk_target(uneven,uc);need(weighted['weights']=={'B':'0.316666666666666666666666','C':'0.316666666666666666666666','D':'0.316666666666666666666668'},'manual exact24place down and lastcode residual')
 calls=[]
 def reader(c,d):calls.append([c,d]);return copy.deepcopy(cells[c])
 seeds={'2024-05-06':seed};sessions=['2024-04-30','2024-05-06','2024-05-07'];targets,receipts,accesses=independent_risk_formations(seeds,sessions,reader);need(accesses==[['A','2024-04-30'],['B','2024-04-30']]==calls,'exact selected source access cadence/order')
 checked=check_risk_target_output_objects(seeds,sessions,reader,targets,receipts,accesses);need(checked['all_targets_independently_reconstructed']==1,'synthetic source object audit')
 negatives=inherited['negative_controls'];changed=copy.deepcopy(cells);changed['A']['future_return']=999;negatives['extra_future_formation_field_rejected']=negative(lambda:independent_risk_target(seed,changed))
 changed=copy.deepcopy(cells);changed['A']['date']='2024-05-06';negatives['execution_day_price_cell_rejected']=negative(lambda:independent_risk_target(seed,changed))
 changed=copy.deepcopy(cells);changed['A']['isST']='';negatives['unknown_state_not_silently_filtered']=negative(lambda:independent_risk_target(seed,changed))
 changedtargets=copy.deepcopy(targets);changedtargets['2024-05-06']['weights']['A']='.95';negatives['changed_target_projection_rejected']=negative(lambda:check_risk_target_output_objects(seeds,sessions,reader,changedtargets,receipts,accesses))
 changedreceipts=copy.deepcopy(receipts);changedreceipts[0]['formation_evidence_id']='0'*64;negatives['changed_formation_evidence_rejected']=negative(lambda:check_risk_target_output_objects(seeds,sessions,reader,targets,changedreceipts,accesses))
 changedaccess=accesses+[['A','2024-05-07']];negatives['unexpected_future_access_receipt_rejected']=negative(lambda:check_risk_target_output_objects(seeds,sessions,reader,targets,receipts,changedaccess))
 def forbidden(c,d):raise RuntimeError('invalid source clock reached provider')
 negatives['future_execution_rejected_before_provider']=negative(lambda:independent_risk_formations({'2026-01-05':{'as_of':'2025-12-31','weights':seed['weights']}},['2025-12-31','2026-01-05'],forbidden))
 # Renaming symbols leaves economics unchanged: no issuer blacklist.
 renamed={'as_of':seed['as_of'],'weights':{'X':.475,'Y':.475}};renamedcells={'X':below['A'],'Y':below['B']};other,_=independent_risk_target(renamed,renamedcells);need(list(other['weights'].values())==list(filtered['weights'].values()),'identity-independent eligibility')
 return {'status':'PASS_SYNTHETIC_MONTHLY_PRICE_RISK_AND_INHERITED_ACCOUNT_AUDIT','policy_id':RISK_POLICY,'contract':RISK_CONTRACT,'inherited_pure_physical_fixture':inherited,'formation_tests':{'one_yuan_boundary':True,'no_op_literal_economic_weights_preserved':True,'allblocked_cash_zero_original_names':True,'manual24decimal_residual':True,'exact_priorclose_accesses':True,'no_ticker_specific_filter':True},'semantic_negative_controls_rejected':negatives,'imports_project_code':False,'real_target_or_quote_or_outcome_read':False,'real_account_or_source_query_run':False,'2026_values_read':False,'draft_waiting_new_wrapper_plan_interface':True}

def all24_synthetic_risk_formations():
 # Explicit synthetic source sessions, not an inferred real exchange calendar.
 seeds={};calendar=set();cells={}
 for year in (2024,2025):
  for month in range(1,13):
   execution=f'{year}-{month:02d}-02';formation=(date(year,month,1)-timedelta(days=1)).isoformat()
   if execution=='2024-01-02':formation='2023-12-29'
   calendar.update((formation,execution));seeds[execution]={'as_of':formation,'weights':{'A':.475,'B':.475}}
   for code in ('A','B'):cells[code,formation]={'date':formation,'close':'.99' if code=='B' and month%2==0 else '1.00','tradestatus':'1','isST':'0'}
 calls=[]
 def read_cell(c,d):calls.append([c,d]);need((c,d) in cells,'synthetic formation cannot access absent/future row');return copy.deepcopy(cells[c,d])
 targets,receipts,accesses=independent_risk_formations(seeds,sorted(calendar),read_cell)
 need(len(targets)==len(receipts)==24 and len(accesses)==48 and accesses==calls,'all24 fixed synthetic formation clocks/48 selected-cell reads')
 need(sum(t['weights']!=seeds[d]['weights'] for d,t in targets.items())==12,'known12 synthetic guard months with no parameter scan')
 return {'all24_synthetic_formations_reconstructed':True,'receipt_count':24,'source_cell_reads':48,'synthetic_changed_months':12,'calendar_is_explicit_synthetic_only':True}

def audit_risk_target_directory(base,repo,folder,request_path,expected_request_sha,original_context):
 """Prepared interface, called only after source generation is explicitly allowed.

 No account replay. All source/cell accesses are reconstructed independently
 against the unchanged seed source, never against post-execution data.
 """
 base,repo,folder,request_path=map(Path,(base,repo,folder,request_path));verify_sha(request_path,expected_request_sha);request=read(request_path)
 need(request['status']=='FROZEN_BEFORE_MONTHLY_PRICE_RISK_REAL_TARGET_GENERATION' and request['contract']==RISK_CONTRACT and request['policy_id']==RISK_POLICY and request['candidate_budget']==1 and request['minimum_formation_raw_close_CNY']=='1.00' and request['surviving_target_budget']=='.95' and request['end']=='2025-12-31' and request['portfolio_returns_permitted'] is False and request['2026_evaluation_permitted'] is False,'one fixed pre2026 target-generation trial')
 expected={**request['input_sha256'],'frozen_risk_target_request':expected_request_sha};paths={k:(repo/k[5:] if k.startswith('repo/') else base/k[7:] if k.startswith('source/') else None) for k in request['input_sha256']};paths['frozen_risk_target_request']=request_path
 need(all(path is not None and path.resolve().is_relative_to(repo.resolve()) or path is not None and path.resolve().is_relative_to(base.resolve()) for path in paths.values()),'all frozen target inputs inside explicit roots')
 for k,path in paths.items():verify_sha(path,expected[k])
 for name,h in request['method_code_sha256'].items():verify_sha(repo/name,h);need(request['input_sha256']['repo/'+name]==h,'target method bound as actual input')
 before={p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()};need(set(before)=={'targets.json','formation_receipts.json','formation_accesses.json','minute_requirements.json','input-before.json','input-postcheck.json','terminal.json','summary.json'},'exact8 target-generation artifacts');need(read(folder/'input-before.json')==expected,'full source-only target input map')
 post=read(folder/'input-postcheck.json');need(post=={'all_inputs_unchanged':True,'count':len(paths),'mismatches':[],'risk_request_rehashed_after_processing':True},'complete target source/request postcheck')
 targets=read(folder/'targets.json');receipts=read(folder/'formation_receipts.json');accesses=read(folder/'formation_accesses.json');seeds=original_context.targets
 def reader(code,day):
  row=original_context.bars[code][day];return {k:row[k] for k in ('date','close','tradestatus','isST')}
 result=check_risk_target_output_objects(seeds,original_context.sessions,reader,targets,receipts,accesses);need(result['all_targets_independently_reconstructed']==24,'all24 actual formation objects required')
 active,skipped=scope_from_targets(targets,original_context.bars,original_context.proofs['lifecycles']);minute={'active_requests':active,'nonexecuting_source_intervals':skipped};need(read(folder/'minute_requirements.json')==minute,'full independent new cumulative minute source scope')
 old=read(repo/MINREQ);need(set(map(tuple,active))<=set(map(tuple,old['active_requests'])) and all(r in old['nonexecuting_source_intervals'] for r in skipped),'no new source pair beyond unchanged authenticated bank')
 terminal=read(folder/'terminal.json');need(terminal=={'status':'RISK_TARGET_GENERATION_TERMINAL','original_error':None,'completed':True,'formation_accesses':accesses,'postcheck':post,'persistence_errors':[],'portfolio_returns_computed':False},'complete source-only target terminal with exact access sequence')
 artifacts={k:sha(folder/k) for k in ('targets.json','formation_receipts.json','formation_accesses.json','minute_requirements.json')};summary=read(folder/'summary.json')
 expected_summary={'status':'MONTHLY_PRICE_RISK_TARGETS_BUILT_ACCOUNT_NOT_RUN','contract':RISK_CONTRACT,'policy_id':RISK_POLICY,'request_sha256':expected_request_sha,'method_code_sha256':request['method_code_sha256'],'seed_target_sha256':sha(base/TARGET),'months':24,'formation_cell_reads':len(accesses),'changed_weight_months':result['changed_weight_months'],'blocked_reason_counts':result['blocked_reason_counts'],'all_filtered_cash_months':result['all_filtered_cash_months'],'new_active_minute_requirements':len(active),'new_nonexecuting_source_intervals':len(skipped),'all_minute_sources_inside_original_bank':True,'artifacts_sha256':artifacts,'actual_positions_changed_by_target_generation':False,'actual_exit_verified':False,'original_targets_or_failed_results_changed':False,'original_account_or_broker_changed':False,'statutory_delisting_classifier':False,'historical_arrival_verified':False,'original_source_admission_overridden':False,'conditional_engineering_only':True,'separate_account_freeze_required':True,'portfolio_returns_computed':False,'2026_quote_or_return_values_read':False,'objective_achieved':False,'input_count':len(paths),'all_inputs_unchanged':True}
 need(summary==expected_summary,'entire independent target summary counts/flags/paths/SHAs')
 for k,path in paths.items():verify_sha(path,expected[k])
 need(before=={p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()},'all8 target outputs unchanged after independent reconstruction')
 return targets,{**result,'target_request_sha256':expected_request_sha,'target_summary_sha256':sha(folder/'summary.json'),'target_all_output_sha256':before,'all_target_inputs_verified_before_after':True,'new_minute_active_pairs':len(active),'new_nonexecuting_intervals':len(skipped)}

BASE_PLAN=PUBLIC+'illiquidity-source-scenario-development-plan.json'
BASE_PLAN_SHA='7a164209327630135689ddfb6a3b4b4b4a3fd885692e6ae2e37500563e298471'
FAILED_DIR='illiquidity-source-scenario-development-20261022'
TARGET_METHODS=ACCOUNT_METHODS|{RISK_METHOD,RISK_BUILDER}
TARGET_PUBLIC=(BASE_PLAN,PUBLIC+'illiquidity-source-scenario-development-results.json',PUBLIC+'illiquidity-source-scenario-development-independent-ledger-audit.json',PUBLIC+'illiquidity-source-scenario-development-run-verification.json',PUBLIC+'illiquidity-source-scenario-development-failure-diagnostic.json',PUBLIC+'amihud-monthly-price-risk-primary-discovery.json',PUBLIC+'amihud-monthly-price-risk-primary-review.json',PUBLIC+'monthly-price-risk-module-code-review.json',PUBLIC+'monthly-price-risk-builder-code-review.json','docs/research/amihud-monthly-price-risk-plan-2026-10-22.md')

def skip_json_value(text,start):
 """Locate an immutable JSON value without decoding skipped price/ledger cells."""
 i=start
 while i<len(text) and text[i].isspace():i+=1
 need(i<len(text),'truncated JSON metadata')
 first=text[i]
 if first=='"':
  i+=1;escape=False
  while i<len(text):
   c=text[i];i+=1
   if escape:escape=False
   elif c=='\\':escape=True
   elif c=='"':return i
  raise AssertionError('unterminated JSON string')
 if first in '{[':
  stack=[first];i+=1
  while i<len(text) and stack:
   c=text[i]
   if c=='"':i=skip_json_value(text,i);continue
   if c in '{[':stack.append(c)
   elif c in '}]':need(stack[-1]+c in ('{}','[]'),'JSON bracket mismatch');stack.pop()
   i+=1
  need(not stack,'truncated JSON container');return i
 while i<len(text) and not text[i].isspace() and text[i] not in ',]}':i+=1
 need(i>start,'empty JSON metadata value');return i

def object_spans(text):
 i=0
 while i<len(text) and text[i].isspace():i+=1
 need(i<len(text) and text[i]=='{','JSON object metadata required');i+=1;out={};decoder=json.JSONDecoder()
 while True:
  while i<len(text) and text[i].isspace():i+=1
  need(i<len(text),'truncated JSON object')
  if text[i]=='}':return out
  key,end=decoder.raw_decode(text,i);need(type(key) is str and key not in out,'unique JSON metadata member');i=end
  while text[i].isspace():i+=1
  need(text[i]==':','JSON key delimiter');i+=1
  while text[i].isspace():i+=1
  end=skip_json_value(text,i);out[key]=(i,end);i=end
  while text[i].isspace():i+=1
  if text[i]==',':i+=1;continue
  need(text[i]=='}','JSON object separator');return out

def member_from_text(text,key):
 spans=object_spans(text);need(key in spans,'required metadata member '+key);a,b=spans[key];return json.loads(text[a:b])
def metadata_member(path,key):return member_from_text(Path(path).read_text(),key)

def four_cell_packet(path):
 """Decode date first and only four requested daily fields, never OHLC/volume.

 Corporate distributions/adjustments and all other quote fields are lexically
 skipped. A later date is rejected before its close can be JSON-decoded.
 """
 text=Path(path).read_text();spans=object_spans(text);instrument=member_from_text(text,'instrument');window=member_from_text(text,'window');need(window==['2023-12-29','2025-12-31'],'original pre2026 raw source window')
 a,b=spans['bars'];i=a+1;bars={}
 while True:
  while text[i].isspace():i+=1
  if text[i]==']':break
  end=skip_json_value(text,i);rowtext=text[i:end];day=member_from_text(rowtext,'date');need(type(day) is str and '2023-12-29'<=day<='2025-12-31' and date.fromisoformat(day).isoformat()==day and day not in bars,'canonical unique source date within pre2026 cap, before price decoding')
  row={key:member_from_text(rowtext,key) for key in ('date','close','tradestatus','isST')};bars[day]=row;i=end
  while text[i].isspace():i+=1
  if text[i]==',':i+=1;continue
  need(text[i]==']','raw bar array separator')
 need(list(bars)==sorted(bars),'ordered original raw source dates');return instrument,bars

def authenticated_primary_metadata_paths(base,repo):
 discovery=read(repo/(PUBLIC+'amihud-monthly-price-risk-primary-discovery.json'));reviewpath=repo/(PUBLIC+'amihud-monthly-price-risk-primary-review.json');review=read(reviewpath);directory=base/RISK_PRIMARY_DIR;manifestpath=directory/'manifest.json';manifest=read(manifestpath)
 verify_sha(manifestpath,discovery['source_manifest_sha256']);verify_sha(reviewpath,discovery['independent_review_sha256']);expected=discovery['formal_primary_file_sha256'];canonical={'capture-manifest.json','szse-listing-rules-2023-08.pdf','sse-delist-rule-2020-12-31.html','sse-delist-rule-2020-12-31.html.txt','sse-delist-2024-01-09.html','sse-delist-2024-01-09.html.txt','szse-page-113.png','szse-page-116.png'}|{'review-'+n for n in review['reading_page_artifact_sha256']}
 need(len(expected)==22 and len(review['reading_page_artifact_sha256'])==14 and set(expected)==canonical and manifest['file_sha256']==expected,'canonical22 primary documents/pages complete')
 need(expected['capture-manifest.json']==review['capture_manifest_sha256'] and len(review['sources'])==3 and {Path(d['local_path']).name for d in review['sources']}=={'szse-listing-rules-2023-08.pdf','sse-delist-rule-2020-12-31.html','sse-delist-2024-01-09.html'},'exact three primary source metadata anchors')
 for d in review['sources']:need(expected[Path(d['local_path']).name]==d['sha256'],'primary review immutable source SHA')
 for n,h in review['reading_page_artifact_sha256'].items():need(expected['review-'+n]==h,'all14 reviewed primary page SHA')
 need(manifest['portfolio_returns_computed'] is False and manifest['historical_arrival_verified'] is False,'primary metadata does not certify outcomes/arrival')
 paths={'source/'+RISK_PRIMARY_DIR+'/manifest.json':manifestpath}
 for n,h in expected.items():need(Path(n).name==n,'safe primary filename');verify_sha(directory/n,h);paths['source/'+RISK_PRIMARY_DIR+'/'+n]=directory/n
 return paths

def authenticated_old307_metadata_paths(base,repo):
 verification=repo/(PUBLIC+'illiquidity-source-scenario-development-run-verification.json');audit=repo/(PUBLIC+'illiquidity-source-scenario-development-independent-ledger-audit.json');expected=metadata_member(verification,'all307_local_output_file_sha256');audited=metadata_member(audit,'all_output_sha256')
 canonical={f'{p}/{c}/{capital}/{name}' for p in PARTICIPATIONS for c in COSTS for capital in CAPITALS for name in ('error.json','failed_account_state.json','failure_trace.json','partial_case.json','tape_accessed_pairs.json')}|{'summary.json','input-before.json','event_source_receipts.json','input-postcheck.json','derived_events.json','terminal.json','case_results.json'}
 need(len(expected)==307 and set(expected)==canonical and expected==audited,'canonical307 old failed account immutable file map')
 verify_sha(audit,metadata_member(verification,'independent_audit_sha256'));need(metadata_member(audit,'plan_sha256')==metadata_member(verification,'plan_sha256')==BASE_PLAN_SHA and metadata_member(audit,'completed_profiles')==0 and metadata_member(audit,'failed_profiles')==60 and metadata_member(audit,'raw_confirmation_passes_independently') is False,'old failed account independent metadata anchor')
 h=metadata_member(verification,'summary_sha256');need(h==metadata_member(audit,'summary_sha256')==expected['summary.json'],'old failure summary immutable hash anchor');verify_sha(repo/(PUBLIC+'illiquidity-source-scenario-development-results.json'),h)
 paths={}
 for n,h in expected.items():path=base/FAILED_DIR/n;verify_sha(path,h);paths['source/'+FAILED_DIR+'/'+n]=path
 return paths,expected

def target_required_paths(base,repo):
 paths=required_account_inputs(base,repo)
 for name in TARGET_METHODS|set(TARGET_PUBLIC):paths['repo/'+name]=repo/name
 paths.update(authenticated_primary_metadata_paths(base,repo));oldpaths,oldmap=authenticated_old307_metadata_paths(base,repo);paths.update(oldpaths);return paths,oldmap

def verify_complete_target_bindings(base,repo,requestfile,expected_sha):
 verify_sha(requestfile,expected_sha);request=read(requestfile)
 need(request['status']=='FROZEN_BEFORE_MONTHLY_PRICE_RISK_REAL_TARGET_GENERATION' and request['contract']==RISK_CONTRACT and request['policy_id']==RISK_POLICY and request['candidate_budget']==1 and request['minimum_formation_raw_close_CNY']=='1.00' and request['surviving_target_budget']=='.95' and request['end']=='2025-12-31' and request['portfolio_returns_permitted'] is False and request['2026_evaluation_permitted'] is False,'one fixed source-only pre2026 policy trial')
 need(set(request['method_code_sha256'])==TARGET_METHODS,'exact mandatory32 original plus risk source methods');paths,oldmap=target_required_paths(base,repo);need(set(paths)==set(request['input_sha256']),'complete source/primary/old307/target input identity set')
 for key,path in paths.items():verify_sha(path,request['input_sha256'][key])
 for name,h in request['method_code_sha256'].items():need(request['input_sha256']['repo/'+name]==h,'method/input identity agrees');verify_sha(repo/name,h)
 return request,paths,oldmap

def standalone_synthetic_tests():
 r=independent_risk_selftests();r['all24_synthetic_fixture']=all24_synthetic_risk_formations();controls=r['semantic_negative_controls_rejected']
 with tempfile.TemporaryDirectory(prefix='monthly-price-source-audit-test-') as temp:
  path=Path(temp)/'synthetic.json';path.write_text(json.dumps({'instrument':'SH600001','window':['2023-12-29','2025-12-31'],'bars':[{'date':'2024-04-30','close':'1.00','tradestatus':'1','isST':'0','open':'88888','future_quote':'must never decode for decisions'}],'account_body':{'cash':'synthetic-private-do-not-parse'},'all_output_sha256':{'x':'a'*64}}))
  code,bars=four_cell_packet(path);need(code=='SH600001' and bars=={'2024-04-30':{'date':'2024-04-30','close':'1.00','tradestatus':'1','isST':'0'}},'only four synthetic source fields materialized');need(metadata_member(path,'all_output_sha256')=={'x':'a'*64},'metadata map read without account body JSON decoding')
  oldhash=sha(path);path.write_text(path.read_text()+' ');controls['changed_frozen_source_SHA_rejected']=negative(lambda:verify_sha(path,oldhash))
  bad={'instrument':'SH600001','window':['2023-12-29','2025-12-31'],'bars':[{'date':'2026-01-05','close':'new2026value-must-not-decode','tradestatus':'1','isST':'0'}]};path.write_text(json.dumps(bad));controls['later_source_date_rejected_before_close_decoding']=negative(lambda:four_cell_packet(path))
 r.update(status='PASS_SYNTHETIC_STANDALONE_MONTHLY_PRICE_RISK_TARGET_AUDIT',account_or_portfolio_ROI_computed=False,old_account_output_bodies_decoded=False,source_fields_decoded=['date','close','tradestatus','isST'],real_target_or_quote_or_outcome_read=False,ready_for_frozen_source_only_audit=True);r.pop('inherited_pure_physical_fixture',None);r.pop('draft_waiting_new_wrapper_plan_interface',None)
 return r

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ('source-root','repo-root','request','expected-request-sha256','output-dir','audit-output'):parser.add_argument('--'+name,required=True)
 a=parser.parse_args();base,repo,folder,out=map(lambda x:Path(x).resolve(),(a.source_root,a.repo_root,a.output_dir,a.audit_output));requestfile=Path(a.request).resolve();need(not out.exists() and not out.is_relative_to(base) and not out.is_relative_to(repo) and not out.is_relative_to(folder),'new external source audit report only')
 controls=standalone_synthetic_tests()['semantic_negative_controls_rejected'];request,paths,old307=verify_complete_target_bindings(base,repo,requestfile,a.expected_request_sha256)
 rm=read(base/RAW/'manifest.json');sessions=read(base/RAW/'calendar.json')['sessions'];verify_sha(base/RAW/'calendar.json',rm['calendar_sha256']);need(len(sessions)==486 and sessions[0]=='2023-12-29' and sessions[-1]=='2025-12-31' and sessions==sorted(set(sessions)),'486 explicit original pre2026 calendar');verify_sha(base/TARGET,rm['target_sha256']);seeds=read(base/TARGET);need(len(seeds)==24,'all24 frozen original seed targets')
 bars={}
 for code,h in rm['per_code_sha256'].items():
  path=base/RAW/'codes'/(code+'.json');verify_sha(path,h);instrument,rows=four_cell_packet(path);need(instrument==code and set(rows)<=set(sessions),'original four-field packet identity/source-session coverage');bars[code]=rows
 need(len(bars)==144 and set(c for seed in seeds.values() for c in seed['weights'])==set(bars),'complete original144 seed union, no new names')
 proof=read(base/PROOF/'reviewed-manifest.json');need(proof['target_sha256']==rm['target_sha256'],'original primary proof/seed target binding');context=SimpleNamespace(targets=seeds,sessions=sessions,bars=bars,proofs=proof)
 targets,result=audit_risk_target_directory(base,repo,folder,requestfile,a.expected_request_sha256,context)
 expected={**request['input_sha256'],'frozen_risk_target_request':a.expected_request_sha256};allpaths={**paths,'frozen_risk_target_request':requestfile}
 for key,path in allpaths.items():verify_sha(path,expected[key])
 oldpaths,aftermap=authenticated_old307_metadata_paths(base,repo);need(aftermap==old307 and len(oldpaths)==307,'all307 old failed outputs unchanged after target reconstruction')
 report={'status':'PASS_INDEPENDENT_MONTHLY_PRICE_RISK_TARGET_AUDIT','audit_code_sha256':sha(__file__),'request_sha256':a.expected_request_sha256,'policy_id':RISK_POLICY,'contract':RISK_CONTRACT,'summary_sha256':result['target_summary_sha256'],'targets_sha256':sha(folder/'targets.json'),'formation_receipts_sha256':sha(folder/'formation_receipts.json'),'formation_accesses_sha256':sha(folder/'formation_accesses.json'),'all24_targets_receipts_and_access_sequence_independently_reconstructed':True,'formation_reconstruction':result,'all_frozen_inputs_checked_before_after':True,'input_count':len(allpaths),'all_input_sha256':expected,'all_output_sha256':result['target_all_output_sha256'],'old307_failed_output_sha256':old307,'old307_failed_output_bodies_decoded':False,'all_original144_raw_packet_SHA_verified':True,'raw_source_fields_decoded':['date','close','tradestatus','isST'],'all_active_source_dates_capped_pre2026':True,'semantic_negative_controls_rejected':controls,'imports_project_code':False,'stdlib_only':True,'source_only':True,'account_or_portfolio_ROI_computed':False,'statutory_delisting_classifier':False,'actual_exit_verified':False,'original_targets_or_failed_results_changed':False,'original_account_or_broker_changed':False,'historical_arrival_verified':False,'original_source_admission_overridden':False,'conditional_engineering_only':True,'separate_account_freeze_required':True,'2026_quote_or_return_values_read':False,'network_or_SDK_called':False,'Parquet_values_decoded':False,'objective_achieved':False,'critical_or_important_findings':[],'scope':'Source-only independent Fraction/integer24decimal formation policy reconstruction, all24 literal target/receipt/access objects and cumulative source-pair requirements, exact8 output files/summary/terminal, all frozen input bytes before/after, canonical22 primary metadata and307 retained old failure file hashes. Only four original pre2026 source fields are decoded; no account output body, simulator, scorer or production module import.','limitations':['One fixed new research heuristic from failed pre2026 development; not a statutory10/20day delisting classification, guaranteed exit, independent economic family or parameter search.','Zero desired weights do not prove actual liquidation. The original unchanged account/lifecycle/tax/integer/execution guards must independently pass before account admission.','Existing archive source contract retains conditional cent-grid/binary32/clock premises; historical arrival, actual liquidity/impact and original240 admission are not upgraded.']}
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps({'status':report['status'],'audit_output':str(out),'audit_code_sha256':sha(__file__),'report_sha256':sha(out)}))
if __name__=='__main__':
 if sys.argv[1:]==['--self-test']:print(json.dumps(standalone_synthetic_tests(),indent=2))
 else:main()
