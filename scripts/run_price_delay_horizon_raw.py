"""Frozen-method continuous daily diagnostic, not minute execution.
Actual execution requires audited sources and an externally frozen request.
"""
import argparse,csv,hashlib,io,json,re,sys,types
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict,fields
from datetime import date
from decimal import Decimal as D,ROUND_HALF_UP
from functools import partial
from pathlib import Path

START,PRE,END='2023-12-29','2025-12-31','2026-10-20'
CAPITAL='1000000';COSTS=(20,40);POLICY='price_delay_d1'
RAW='price-delay-raw-horizon-v2-20261021';OLDRAW='price-delay-raw-dev-20261021'
TARGET='price-delay-horizon-formations-20261021/candidate_targets.json';OLDTARGET='price-delay-pre2026-formations-20261021/targets.json'
EVENTS='price-delay-account-horizon-events-20261021';OLDEVENTS='price-delay-account-source-events-20261021'
OLDDAY='price-delay-raw-daily-pre2026-20261021';OLDINTRA='price-delay-intraday-pre2026-20261021';OLDSCOPE='price-delay-ordinary-source-scope-20261021'
OUTPUT='price-delay-raw-daily-horizon-20261021'
PROTOCOL='docs/research/price-delay-horizon-account-continuation-plan-2026-10-21.md'
TARGET_SHA='5d122dac55da8f57934524de0b6e3640a303363aca49e0a0a09dd70d5850a923'
RAW_SHA='9fe3990c0b4b1c076b78c97971ceecf593687b2f15699154c3bdbbce666f6490'
PROOFDIR='price-delay-horizon-corporate-reviewed-20261021'
OLDADMIT='price-delay-minute-admission-20261021';OLDCAP='price-delay-minutes-dev-20261021'
PRIOR_AUDIT_SHA={
 'price-delay-raw-daily-independent-ledger-audit.json':'90de13126531e933adc2e68175b466e3fd420e081dccdedf3460182155483dd3',
 'price-delay-intraday-independent-ledger-audit.json':'78f22bc9c7e083cae6422c99b502988b7f6e3741f4ea90fddb453333d9a72e08',
 'price-delay-event-source-independent-audit.json':'934b8a825b3d4662f7bd8f54fb87c6136801a71aee4efd99db7a9ae74af7d201',
 'price-delay-ordinary-source-scope-independent-audit.json':'1783b65e6f472ccabfecd52b5546751c0680cff1210cc62c022ff619288ee2e4',
 'price-delay-horizon-formation-independent-audit.json':'e742386b1a6df1be95c5798fbc3596d0ec6f248df35df436626c75ea26f6507a',
 'price-delay-horizon-local-reassembly-independent-audit.json':'a7bf3324200deb497ba93327fe41c2d4e6ae7fb5b39d7ed81916aaca91ded753'}
RAW_AUDIT='experiments/qlib/price-delay-horizon-local-reassembly-independent-audit.json'
EVENT_AUDIT='experiments/qlib/price-delay-horizon-event-source-independent-audit.json'
EVENT_AUDIT_STATUS='INDEPENDENT_PRICE_DELAY_HORIZON_EVENTS_AND_SOURCE_RECEIPTS_RECONSTRUCTED'
EVENT_AUDIT_CODE='experiments/qlib/audit_sources/2026-10-21-price-delay-horizon-event-source-audit.py'
ARTIFACTS=('daily.csv','intents.json','orders.json','fills.json','corporate_ledger.json','ownership.json')
EVENT_ARTIFACTS=('derived_events.json','event_source_receipts.json','effective_2026_proofs.json','original_derived_events.json','original_event_source_receipts.json')
METHOD_FILES=('scripts/run_price_delay_horizon_raw.py','scripts/run_price_delay_raw_pre2026.py','scripts/prepare_price_delay_account_sources_pre2026.py',
 'scripts/replay_stock_distribution_targets.py','scripts/replay_ordinary_stock_distribution_targets.py',
 'scripts/run_low_risk_raw_share_validation.py','scripts/run_low_risk_feedback_cost_stress.py',
 'scripts/prepare_low_beta60_extension_events.py','scripts/prepare_price_delay_horizon_events.py',
 'src/stock_rsi/distribution_event_compiler_v3.py','src/stock_rsi/distribution_event_compiler_v2.py',
 'src/stock_rsi/distribution_event_compiler.py','src/stock_rsi/stock_distribution_account.py',
 'src/stock_rsi/raw_share_account.py','src/stock_rsi/execution_cost.py','src/stock_rsi/broker.py',
 'src/stock_rsi/ordinary_source_scope.py','src/stock_rsi/lifecycle_source_rows.py',
 'src/stock_rsi/calendar.py','src/stock_rsi/data.py','src/stock_rsi/models.py','src/stock_rsi/time.py',
 'scripts/capture_low_risk_raw_account_data.py','scripts/capture_cninfo_csi500_reports_pre2026.py',
 'scripts/prepare_qlib_master_market_pre2026.py')
PUBLIC_FILES=(PROTOCOL,RAW_AUDIT,EVENT_AUDIT,EVENT_AUDIT_CODE,
 'experiments/qlib/price-delay-raw-daily-independent-ledger-audit.json',
 'experiments/qlib/price-delay-ordinary-source-scope-independent-audit.json',
 'experiments/qlib/price-delay-horizon-formation-independent-audit.json',
 'experiments/qlib/price-delay-raw-daily-plan.json',
 'experiments/qlib/price-delay-intraday-independent-ledger-audit.json',
 'experiments/qlib/price-delay-event-source-independent-audit.json')
LOCAL_FILES=(RAW+'/manifest.json',RAW+'/calendar.json',OLDRAW+'/manifest.json',OLDRAW+'/calendar.json',
 TARGET,OLDTARGET,'price-delay-horizon-formations-20261021/summary.json',EVENTS+'/summary.json',*(EVENTS+'/'+n for n in EVENT_ARTIFACTS),
 OLDEVENTS+'/summary.json',OLDEVENTS+'/derived_events.json',OLDEVENTS+'/event_source_receipts.json',
 'price-delay-horizon-corporate-reviewed-20261021/reviewed-manifest.json',
 OLDDAY+'/summary.json',OLDINTRA+'/summary.json',OLDSCOPE+'/summary.json',OLDSCOPE+'/scope.json',OLDADMIT+'/summary.json',OLDADMIT+'/details.json',OLDCAP+'/manifest.json')
PROFILE={'status':'FROZEN_PRICE_DELAY_CONTINUOUS_RAW_DAILY_HORIZON_DIAGNOSTIC','candidate':POLICY,
 'initial_CNY':CAPITAL,'extra_cost_bps':[20,40],'window':[START,END],'output_directory':OUTPUT,
 'allocator':'plan_integer_targets','account_guard':'ordinary_source_rows_on',
 'new_source_queries':0,'investment_rules_changed':False,'full_October_2026_complete':False,
 'original_strict_minute_admission_stays_failed':True,'all_profile_gates_before_any_annual_returns':True}
def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def need(x,msg):
 if not x:raise ValueError(msg)
def safe(root,name):
 p=Path(root)/name;need(not Path(name).is_absolute() and '..' not in Path(name).parts and p.resolve().is_relative_to(Path(root).resolve()),'safe frozen path required');return p
def clean(x):
 if isinstance(x,(date,D)):return str(x)
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [clean(v) for v in x]
 return x
def write_json(p,x):Path(p).write_text(json.dumps(clean(x),indent=2)+'\n')
def require_profile(plan):
 need(all(type(plan.get(k)) is type(v) and plan[k]==v for k,v in PROFILE.items()),'fixed continuous1m/20,40/finalOct20/profile required')
 for key,names in [('method_code_sha256',METHOD_FILES),('public_evidence_sha256',PUBLIC_FILES),('local_source_sha256',LOCAL_FILES)]:need(set(plan[key])==set(names),'complete mandatory binding set '+key)
def verify_maps(base,repo,plan):
 for key,root in [('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base),('immutable_financial_sha256',base)]:
  for n,h in plan[key].items():need(sha(safe(root,n))==h,'frozen input changed '+n)
def immutable_financials(base):
 result={}
 for root,key,labels,names in [(OLDDAY,'results_by_extra_bps',{'20','40'},set(ARTIFACTS)),(OLDINTRA,'results_by_profile',{f'{p}/{c}' for p in (100,500,1000) for c in COSTS},set(ARTIFACTS)|{'parent_instructions.json','source_scope_audit.json'})]:
  results=read(base/root/'summary.json')[key];need(set(results)==labels,'exact original profile family')
  for label,r in results.items():
   need(set(r['artifact_sha256'])==names,'exact original artifact scope')
   for name,h in r['artifact_sha256'].items():need(sha(base/root/label/name)==h,'oldfinancial changed');result[root+'/'+label+'/'+name]=h
 need(len(result)==60,'old12raw+48intraday immutable files required');return result

def project_account_bars(packets,old_codes,targets):
 """Evaluator window projection; source packets remain full/unchanged."""
 first=min(d for d in targets if d>PRE);need(targets[first]['as_of']==PRE,'first2026 target must form on Dec31')
 boundary=set(targets[first]['weights'])-set(old_codes);bars={}
 for c,p in packets.items():
  rows={}
  for r in p['bars']:
   day=r['date']
   if c in old_codes or day>PRE:rows[day]=deepcopy(r)
   elif c in boundary and day==PRE:
    # New-name exception is a close-state record, not its prior OHLC/volume history.
    rows[day]={k:r[k] for k in ('date','code','close','tradestatus','isST')}
  bars[c]=rows
 return bars,boundary

def make_simulator(old_codes,boundary):
 """Original function code/allocator; only evaluator source-view binding differs."""
 from scripts.replay_stock_distribution_targets import simulate_fixed_targets as original
 from stock_rsi.ordinary_source_scope import ordinary_source_rows_on
 audit=[]
 def guarded(bars,day,required,lifecycles):
  d=day.isoformat();visible={c:v for c,v in bars.items() if c in old_codes or d>PRE or d==PRE and c in boundary}
  need(set(required)<=set(visible),'future-only pre2026 account dependency outside Dec31 exception')
  rows,exceptions=ordinary_source_rows_on(visible,day,required,lifecycles);audit.extend(deepcopy(exceptions));return rows,exceptions
 namespace=dict(original.__globals__);namespace['source_rows_on']=guarded
 cloned=types.FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__);cloned.__kwdefaults__=original.__kwdefaults__
 return cloned,audit

def partial_progress(exc,simulation):
 tb=exc.__traceback__
 while tb:
  if tb.tb_frame.f_code is simulation.__code__:
   v=tb.tb_frame.f_locals
   return clean({key:v.get(key,[]) if key!='ownership' else v.get(key,{}) for key in ('rows','intents','ownership','lifecycle_audit')})
  tb=tb.tb_next
 return {}
def checkpoint_account_type():
 from stock_rsi.stock_distribution_account import StockDistributionAccount
 class CheckpointAccount(StockDistributionAccount):
  def end_day(self,day):
   super().end_day(day)
   if day.isoformat()==PRE and not hasattr(self,'pre2026_checkpoint'):
    self.pre2026_checkpoint=deepcopy(clean({k:getattr(self.broker,k) if k in ('orders','fills') else self.corporate_ledger for k in ('orders','fills','corporate_ledger')}))
 return CheckpointAccount

def source_scope_expected(raw_bars,old_codes,boundary,sessions):
 result=[]
 for day in sessions:
  for c,byday in sorted(raw_bars.items()):
   if c not in old_codes and day<=PRE and not(day==PRE and c in boundary):continue
   if byday[day].get('isST')=='1':result.append({'instrument':c,'session':day,'reason':'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT','original_row_present':True,'source_isST':'1','required_by_account':False,'synthetic_price_created':False})
 return result

def prefix_artifact_hashes(case,checkpoint):
 olddays=[r for r in case['days'] if r['day']<=PRE];need(olddays,'nonempty old daily prefix required');stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=list(olddays[0]));w.writeheader();w.writerows(olddays)
 values={'daily.csv':hashlib.sha256(stream.getvalue().encode()).hexdigest()}
 objects={k:checkpoint[k] for k in ('orders','fills','corporate_ledger')};objects['intents']=[r for r in case['intents'] if r['execution_session']<=PRE];objects['ownership']={d:v for d,v in case['ownership'].items() if d<=PRE}
 for k,v in objects.items():values[k+'.json']=hashlib.sha256((json.dumps(clean(v),indent=2)+'\n').encode()).hexdigest()
 return values

def verify_prefix(case,checkpoint,reference,old_scope):
 need(checkpoint is not None,'end2025 checkpoint missing before crossyear instruction')
 need(prefix_artifact_hashes(case,checkpoint)==reference['artifact_sha256'],'old six financial serialized prefix bytes changed')
 for k in ('orders','fills','corporate_ledger'):need(checkpoint[k]==reference[k],'old boundary collection changed '+k)
 # eligible/execution clocks assign the Dec31->Jan instruction to2026.
 need(clean([r for r in case['intents'] if r['execution_session']<=PRE])==reference['intents'],'old intention/snapshot prefix changed')
 need(clean({d:v for d,v in case['ownership'].items() if d<=PRE})==reference['ownership'],'old listed integer ownership changed')
 need([{k:str(v) for k,v in r.items()} for r in case['days'] if r['day']<=PRE]==reference['days'],'old daily cash/assets/fees changed')
 need([r for r in case['lifecycle_source_audit'] if r['session']<=PRE]==old_scope,'old ordinary dependency audit changed')
 # Later mutations of old order statuses are not read backwards as boundary data.
 need(all(r.get('eligible_at') is None or r['eligible_at'][:10]<=PRE for r in checkpoint['orders']),'boundary checkpoint contains future eligible instructions')

def decode_events(rows,calendar):
 from stock_rsi.stock_distribution_account import StockDistribution,StockDistributionAccount
 out=[];names={f.name for f in fields(StockDistribution)}
 for row in rows:
  need(set(row)==names,'exact serialized StockDistribution fields');v=dict(row)
  for k in ('announced','recorded','ex_date','pay_date','listed'):
   if v[k] is None and k in ('pay_date','listed'):continue
   need(isinstance(v[k],str),'serialized date string required');d=date.fromisoformat(v[k]);need(d.isoformat()==v[k],'canonicaleventday');v[k]=d
  for k in ('cash_per_share','capital_per_share','stock_per_share','stock_taxable_income_per_share'):
   need(isinstance(v[k],str),'serialized Decimal string required');v[k]=D(v[k]);need(v[k].is_finite() and v[k]>=0,'finite nonnegative event component')
  for k in ('capital_tax_exempt_verified','stock_tax_basis_verified'):need(type(v[k]) is bool,'typed tax flags')
  out.append(StockDistribution(**v))
 StockDistributionAccount(calendar,'1',out,tax_reserve_rate='.2') # validation only; never starts a day
 return tuple(out)

def verify_event_audit(audit,summary,source,plan,repo):
 """Proposed exact interface; bind actual independent audit before freezing."""
 required=('original378_events_and_receipts_identical','all_source_receipts_reconstructed','all_original151_source_prefixes_identical','unknown_tax_guards_preserved')
 need(audit['status']==EVENT_AUDIT_STATUS and not audit['critical_or_important_findings'],'successful event source audit status required')
 need(audit['summary_sha256']==sha(source/'summary.json')==plan['event_summary_sha256'] and audit['events_reconstructed']==plan['compiled_event_count'] and audit['imports_project_code'] is False and all(audit.get(k) is True for k in required),'complete independent event source audit required')
 controls=audit.get('negative_controls_rejected');need(isinstance(controls,dict) and len(controls)>=4 and all(v is True for v in controls.values()),'event audit negative controls required')
 need(audit['audit_code_sha256']==sha(repo/EVENT_AUDIT_CODE) and audit['raw_manifest_sha256']==summary['raw_manifest_sha256']==RAW_SHA and summary['target_sha256']==TARGET_SHA,'event audit/raw/target lineage')
 need(audit['derived_events_sha256']==sha(source/'derived_events.json') and audit['event_source_receipts_sha256']==sha(source/'event_source_receipts.json') and audit['effective_2026_proofs_sha256']==sha(source/'effective_2026_proofs.json'),'event audit actual compiled bytes anchors')

def load_inputs(base,repo,plan):
 from stock_rsi.calendar import TradingCalendar
 require_profile(plan);verify_maps(base,repo,plan)
 for n,h in PRIOR_AUDIT_SHA.items():need(sha(repo/'experiments/qlib'/n)==h,'previous independently audited report bytes changed '+n)
 financial=immutable_financials(base);need(financial==plan['immutable_financial_sha256'],'exact all60 financial bindings')
 da=read(repo/'experiments/qlib/price-delay-raw-daily-independent-ledger-audit.json');ia=read(repo/'experiments/qlib/price-delay-intraday-independent-ledger-audit.json');ea=read(repo/'experiments/qlib/price-delay-event-source-independent-audit.json')
 need(da['status']=='PASS_INDEPENDENT_PRE2026_RAW_DAILY_DECIMAL_LEDGER_AUDIT' and da['summary_sha256']==sha(base/OLDDAY/'summary.json') and da['all378_source_events_and_15_PDF_review_bindings_unchanged'] is True and da['production_simulate_summarize_reconcile_imported_or_called'] is False and not da['critical_or_important_findings'],'old independently audited complete raw account required')
 need(ia['status']=='INDEPENDENT_SIX_PRICE_DELAY_INTRADAY_ACCOUNT_LEDGERS_RECONSTRUCTED' and ia['summary_sha256']==sha(base/OLDINTRA/'summary.json') and ia['all_six_profile_ledgers_reconstructed'] is True and ia['imports_project_code'] is False and not ia['critical_or_important_findings'],'old independently audited complete intraday evidence required')
 need({OLDDAY+'/'+n:h for n,h in da['all12_financial_artifact_sha256'].items()}|{OLDINTRA+'/'+n:h for n,h in ia['all48_financial_artifact_sha256'].items()}==financial,'all60 physical financial bytes must match audited versions')
 need(da['source_audit_sha256']==ia['source_event_audit_sha256']==sha(repo/'experiments/qlib/price-delay-event-source-independent-audit.json') and ea['summary_sha256']==sha(base/OLDEVENTS/'summary.json'),'old source event audit lineage')
 fa=read(repo/'experiments/qlib/price-delay-horizon-formation-independent-audit.json');need(fa['summary_sha256']==sha(base/'price-delay-horizon-formations-20261021/summary.json') and fa['artifact_sha256']['candidate_targets.json']==TARGET_SHA and fa['all34_formations_independently_reconstructed'] is True and fa['original24_prefix_identical'] is True and fa['imports_project_code'] is False,'independent34formation summary/targets anchor')
 need(sha(base/RAW/'manifest.json')==RAW_SHA and sha(base/TARGET)==TARGET_SHA,'frozenraw/targetidentity')
 rm=read(base/RAW/'manifest.json');ra=read(repo/RAW_AUDIT);need(ra['manifest_sha256']==RAW_SHA and ra['imports_project_code'] is False and ra['all203_packets_676_sessions_verified'] is True and ra['all151_original_literal_pre2026_prefixes_identical'] is True,'independent203raw source audit')
 need(sha(base/RAW/'calendar.json')==rm['calendar_sha256'],'calendarSHA');sessions=read(base/RAW/'calendar.json')['sessions'];old_sessions=read(base/OLDRAW/'calendar.json')['sessions'];need(len(sessions)==676 and sessions==sorted(set(sessions)) and sessions[:486]==old_sessions and [sessions[0],sessions[-1]]==[START,END],'676completeold486calendar')
 packets={};old=read(base/OLDRAW/'manifest.json');need(da['all151_raw_source_packet_sha256']==old['per_code_sha256'],'original151 physical raw hashes match account audit');need(len(old['per_code_sha256'])==151 and len(rm['per_code_sha256'])==203,'151old52additional names')
 for c,h in rm['per_code_sha256'].items():
  f=base/RAW/'codes'/(c+'.json');need(sha(f)==h,'rawpacketSHA');p=read(f);need(p['instrument']==c and p['window']==[START,END] and [r['date'] for r in p['bars']]==sessions,'raw completecalendar');packets[c]=p
  if c in old['per_code_sha256']:
   f=base/OLDRAW/'codes'/(c+'.json');need(sha(f)==old['per_code_sha256'][c],'originalpacketSHA');op=read(f)
   for name,key in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:need([r for r in p[name] if r[key]<=PRE]==op[name],'literal151rawprefix')
 targets=read(base/TARGET);prior=read(base/OLDTARGET)[POLICY];need(len(targets)==34 and len(prior)==24 and {d:v for d,v in targets.items() if d<=PRE}==prior and {c for t in targets.values() for c in t['weights']}==set(packets),'frozen34/24targets203universe')
 for d,t in targets.items():need(d in sessions and sessions.index(d)>0 and t['as_of']==sessions[sessions.index(d)-1],'fixedtargetpriorclose')
 source=base/EVENTS;ss=read(source/'summary.json');need(ss['old_source_summary_sha256']==sha(base/OLDEVENTS/'summary.json'),'old event summary lineage');audit=read(repo/EVENT_AUDIT);need(sha(repo/EVENT_AUDIT)==plan['event_audit_sha256'],'external event audit identity');verify_event_audit(audit,ss,source,plan,repo)
 need(set(ss['artifact_sha256'])==set(EVENT_ARTIFACTS),'exactcompiled artifactscope')
 for n,h in ss['artifact_sha256'].items():need(sha(source/n)==h,'compiledeventartifactSHA')
 rows=read(source/'derived_events.json');receipts=read(source/'event_source_receipts.json');oldrows=read(base/OLDEVENTS/'derived_events.json');oldrec=read(base/OLDEVENTS/'event_source_receipts.json')
 need(len(oldrows)==len(oldrec)==378 and rows[:378]==oldrows and receipts[:378]==oldrec and len(rows)==len(receipts)==plan['compiled_event_count'],'exact378orderedobjectandreceiptprefix')
 need(len({r['event_id'] for r in rows})==len(rows) and all(r['event_id']==e['event_id'] and r['instrument']==e['instrument'] and r['ex_date']==e['ex_date'] for e,r in zip(rows,receipts)),'pairedcompiledids')
 need(all(e['ex_date']>PRE and e['recorded']>PRE for e in rows[378:]),'no future-only pre26distribution leakage')
 calendar=TradingCalendar(sessions);events=decode_events(rows,calendar)
 need(all(type(r['requires_zero_record_ownership_if_tax_unverified']) is bool and r['requires_zero_record_ownership_if_tax_unverified']==bool(e.capital_per_share>0 and not e.capital_tax_exempt_verified or e.stock_per_share>0 and not e.stock_tax_basis_verified) for e,r in zip(events,receipts)),'typed paired unknown-tax receipt guards')
 proof=read(source/'effective_2026_proofs.json')
 need(audit['reviewed_manifest_sha256']==ss['reviewed_manifest_sha256']==sha(base/PROOFDIR/'reviewed-manifest.json'),'event audit primary proof projection anchor')
 reviewed=read(base/PROOFDIR/'reviewed-manifest.json')
 docs=reviewed['documents'].values() if isinstance(reviewed['documents'],dict) else reviewed['documents']
 for doc in docs:
  f=safe(base/PROOFDIR,doc['file']);need(sha(f)==doc['sha256'] and f.read_bytes().startswith(b'%PDF'),'actual reviewed original PDF bytes changed')
 unsafe={e.instrument+'|'+e.ex_date.isoformat() for e in events[378:] if (e.capital_per_share>0 and not e.capital_tax_exempt_verified) or(e.stock_per_share>0 and not e.stock_tax_basis_verified)}
 need(unsafe==set(plan['unresolved_2026_event_keys']) and set(proof['unresolved_tax'])==unsafe and all(v.get('verified_exempt') is False for v in proof['unresolved_tax'].values()) and not unsafe&set(proof.get('capital_tax',{})),'exact unresolved tax guards remainfalse')
 refs={};oldresults=read(base/OLDDAY/'summary.json')['results_by_extra_bps']
 for bps in COSTS:
  f=base/OLDDAY/str(bps);r={'artifact_sha256':oldresults[str(bps)]['artifact_sha256']}
  with(f/'daily.csv').open() as stream:r['days']=list(csv.DictReader(stream))
  for n in ('intents','orders','fills','corporate_ledger','ownership'):r[n]=read(f/(n+'.json'))
  refs[bps]=r
 scope=read(base/OLDSCOPE/'scope.json');sa=read(repo/PUBLIC_FILES[5]);need(sa['source_scope_sha256']==sha(base/OLDSCOPE/'scope.json') and sa['ordinary_scope_reconstructed'] is True and sa['imports_project_code'] is False and len(scope['nonordinary_source_intervals'])==241,'old independentordinaryscope')
 failed=read(base/OLDADMIT/'summary.json');need(failed['admitted_for_reconstructed_execution'] is False and sa['original_failed_admission_summary_sha256']==sha(base/OLDADMIT/'summary.json') and sa['original_failed_admission_details_sha256']==sha(base/OLDADMIT/'details.json') and sa['original_strict_admission_remains_failed'] is True,'original failed strict minute admission stays false')
 need(len(scope['rejected_packet_sha256'])==12,'retained12 ST evidence')
 for n,h in scope['rejected_packet_sha256'].items():need(sha(base/OLDCAP/'sessions'/n)==h,'retained rejected ST packet bytes changed')
 old_scope=[{'instrument':r['instrument'],'session':r['day'],'reason':'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT','original_row_present':True,'source_isST':'1','required_by_account':False,'synthetic_price_created':False} for r in scope['nonordinary_source_intervals']]
 bars,boundary=project_account_bars(packets,set(old['per_code_sha256']),targets)
 return {'calendar':calendar,'sessions':sessions,'packets':packets,'raw_bars':{c:{r['date']:r for r in p['bars']} for c,p in packets.items()},'bars':bars,'old_codes':set(old['per_code_sha256']),'boundary_codes':boundary,'events':events,'targets':targets,'references':refs,'old_scope':old_scope,'receipts':receipts}

# Runtime conservation validation is separate from annual-return calculation.
def reconcile_case(case,events,bars,sessions,cost):
 need([r['day'] for r in case['days']]==sessions and len(case['ownership'])==len(sessions),'complete unique daily path')
 byid={e.event_id:e for e in events};corp=defaultdict(list);fills=defaultdict(list)
 for r in case['corporate_ledger']:corp[str(r['day'])].append(r)
 for f in case['fills']:fills[f['execution_at'][:10]].append(f)
 cash=D(CAPITAL);previous_equity=cash;lots={};pending=[];claims={};registered={};marks={}
 for row in case['days']:
  day=row['day'];fees=D(0);paid=D(0)
  # Opening corporate rows precede trading; record ownership follows trading.
  for r in corp[day]:
   if r['kind']=='RECORD_DATE_OWNERSHIP':continue
   e=byid[r['event_id']];k=r['kind']
   if k=='NET_DIVIDEND_CASH_AVAILABLE':
    claim=claims.pop(e.event_id);need(claim['available']==day and r['cash_delta']==claim['net'],'cash availability conservation');cash+=claim['net'];paid+=claim['net']
   elif k=='EX_DATE_ENTITLEMENT':
    need(e.recorded.isoformat()<sessions[0] or e.event_id in registered,'recorddate must be observed');q=registered.get(e.event_id,0);need(r['registered_quantity']==q,'actualregisteredshares');capital=e.capital_per_share*q;stock=e.stock_per_share*q;need(capital==capital.to_integral_value() and stock==stock.to_integral_value(),'fractionalguard');need(not q or not e.capital_per_share or e.capital_tax_exempt_verified,'unknowncapitalguard');need(not q or not e.stock_per_share or e.stock_tax_basis_verified and e.stock_taxable_income_per_share>0,'unknownstockguard')
    gross=(e.cash_per_share*q).quantize(D('.01'),rounding=ROUND_HALF_UP);income=(e.stock_taxable_income_per_share*q).quantize(D('.01'),rounding=ROUND_HALF_UP);reserve=((gross+income)*D('.2')).quantize(D('.01'),rounding=ROUND_HALF_UP)
    need(reserve<=gross,'stock reserve exceeds cash');need(r['cash_gross']==gross and r['stress_tax_reserve']==reserve and r['capital_shares']==int(capital) and r.get('stock_shares',0)==int(stock),'corporateeconomics')
    if gross:claims[e.event_id]={'net':gross-reserve,'available':next((d for d in sessions if d>e.pay_date.isoformat()),None)}
    for qty,kind in [(int(capital),'CAPITAL_SHARES_LISTED'),(int(stock),'STOCK_DIVIDEND_SHARES_LISTED')]:
     if qty:pending.append({'event_id':e.event_id,'instrument':e.instrument,'quantity':qty,'kind':kind,'listed':e.listed.isoformat(),'recorded':e.recorded.isoformat()})
   elif k in ('CAPITAL_SHARES_LISTED','STOCK_DIVIDEND_SHARES_LISTED'):
    matches=[p for p in pending if p['event_id']==e.event_id and p['kind']==k];need(len(matches)==1 and matches[0]['quantity']==r['quantity'] and matches[0]['listed']<=day,'listedstockconservation');p=matches[0];pending.remove(p);lots.setdefault(e.instrument,[]).append({'quantity':p['quantity'],'bought_on':p['recorded']})
   else:raise ValueError('unknowncorporateledgerkind')
  byvolume=defaultdict(int)
  for f in fills[day]:
   c=f['security_id'];q=f['quantity'];price=D(f['price']);need(type(q) is int and 0<q<=1000000 and f['action'] in ('BUY','SELL'),'physicalfill');gross=price*q;fee=max(D('5'),gross*D('0.0005' if f['action']=='BUY' else '0.0015')).quantize(D('.01'),rounding=ROUND_HALF_UP)+(gross*D(cost)/10000).quantize(D('.01'),rounding=ROUND_HALF_UP);need(D(f['cost'])==fee,'samebaseandextrafeeformula');fees+=fee;byvolume[c]+=q
   if f['action']=='BUY':need(q%100==0,'100sharebuy');cash-=gross+fee;lots.setdefault(c,[]).append({'quantity':q,'bought_on':day})
   else:
    need(sum(l['quantity'] for l in lots.get(c,[]) if l['bought_on']<day)>=q,'Tplus1FIFO');cash+=gross-fee;remain=q
    for l in lots.get(c,[]):
     if l['bought_on']>=day:continue
     used=min(l['quantity'],remain);l['quantity']-=used;remain-=used
    lots[c]=[l for l in lots[c] if l['quantity']]
    if not lots[c]:del lots[c]
   need(cash==D(f['cash_after']) and cash>=0,'fillcashconservation')
  for c,q in byvolume.items():need(D(bars[c][day]['volume'])>=q,'unsupported whole-day volume')
  listed={c:sum(l['quantity'] for l in ls) for c,ls in lots.items()}
  for r in corp[day]:
   if r['kind']=='RECORD_DATE_OWNERSHIP':need(r['quantity']==listed.get(r['instrument'],0),'recordownership');registered[r['event_id']]=r['quantity']
  for c in set(listed)|{p['instrument'] for p in pending}:
   source=bars[c][day]
   if source['tradestatus']=='1':marks[c]=D(source['close'])
   elif any(e.instrument==c and e.ex_date.isoformat()==day for e in events):marks[c]=D(source['preclose'])
   elif c not in marks:marks[c]=D(source['close'])
  mv=sum((q*marks[c] for c,q in listed.items()),D(0));pv=sum((p['quantity']*marks[p['instrument']] for p in pending),D(0));rv=sum((x['net'] for x in claims.values()),D(0));equity=cash+mv+pv+rv
  need(case['ownership'][day]==listed and row['cash']==cash and row['market_value']==mv and row['pending_stock_value']==pv and row['cash_receivable']==rv and row['equity']==equity and row['fees']==fees and row['net_dividend_cash_available']==paid,'dailycash/share/claims/equityconservation');need(equity.is_finite() and equity>0 and row['exposure']==(mv+pv)/equity and row['net_return']==equity/previous_equity-1,'dailyfinitepositiveequityandexposure');previous_equity=equity
 return True

def validate_case(case,checkpoint,reference,inputs,cost):
 need([r['day'] for r in case['days']]==inputs['sessions'] and [r['execution_session'] for r in case['intents']]==sorted(inputs['targets']) and len(case['intents'])==34 and case['whole_day_volume_violations']==0,'full676/34/no observedcapacityviolation required')
 verify_prefix(case,checkpoint,reference,inputs['old_scope'])
 need(case['lifecycle_source_audit']==source_scope_expected(inputs['raw_bars'],inputs['old_codes'],inputs['boundary_codes'],inputs['sessions']),'completeordinarydependency audit')
 reconcile_case(case,inputs['events'],inputs['bars'],inputs['sessions'],cost)
 return True

def write_case(folder,case,checkpoint):
 with (folder/'daily.csv').open('w',newline='') as stream:
  w=csv.DictWriter(stream,fieldnames=list(case['days'][0]));w.writeheader();w.writerows(case['days'])
 for k in ('intents','orders','fills','corporate_ledger','ownership'):write_json(folder/(k+'.json'),case[k])
 write_json(folder/'source_scope_audit.json',case['lifecycle_source_audit']);write_json(folder/'pre2026_checkpoint.json',checkpoint)
 return {p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()}
def preserve_failure(folder,exc,holders,simulation,audit,completed_case=None):
 result={'status':'INVALID_SOURCE_OR_ACCOUNT','error_type':type(exc).__name__,'error':str(exc),'portfolio_returns_computed':False}
 if holders:
  a=holders[0];write_json(folder/'failed_account_state.json',{'last_account_clock':a._last_clock,'cash':a.broker.cash,'positions':a.broker.positions,'owned_shares':a.owned_quantities(),'orders':a.broker.orders,'fills':a.broker.fills,'entitlements':a.entitlements,'corporate_ledger':a.corporate_ledger,'cash_claims':a.cash_claims,'stock_claims':a.stock_claims,'pre2026_checkpoint':getattr(a,'pre2026_checkpoint',None)})
 progress=partial_progress(exc,simulation)
 if completed_case is not None:write_json(folder/'unvalidated_completed_case.json',completed_case)
 write_json(folder/'partial_case.json',progress);write_json(folder/'source_scope_audit.json',audit);write_json(folder/'error.json',result);result['failure_artifact_sha256']={p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()};return result

def annual_returns(case):
 nav={r['day']:r['equity'] for r in case['days']};v=[D(CAPITAL),nav['2024-12-31'],nav[PRE],nav[END]];need(all(x.is_finite() and x>0 for x in v),'positivefiniteannualdenominators');r=[v[i+1]/v[i]-1 for i in range(3)]
 return {'2024_return_pct':float(r[0]*100),'2025_return_pct':float(r[1]*100),'2026_through_2026-10-20_return_pct':float(r[2]*100),'2026_starting_equity':str(v[2]),'ending_equity':str(v[3]),'three_numeric_conditions_met_at_interim_cutoff':r[0]>0 and r[1]>0 and r[2]>=D('.1')}
def finalize_returns(results,cases,postcheck,scorer=annual_returns):
 if not postcheck or set(results)!={'20','40'} or set(cases)!={20,40} or any(r['status']!='CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED' for r in results.values()):return False
 for cost in COSTS:results[str(cost)].update(scorer(cases[cost]),portfolio_returns_computed=True)
 return True

def run_profiles(out,inputs,*,postcheck,scorer=annual_returns):
 from stock_rsi.execution_cost import ExecutionCostBroker
 out=Path(out);need(not out.exists(),'preserve previous complete/failed run');out.mkdir(parents=True);results={};cases={};Account=checkpoint_account_type()
 for cost in COSTS:
  folder=out/str(cost);folder.mkdir();holders=[];case=None;simulation,audit=make_simulator(inputs['old_codes'],inputs['boundary_codes'])
  def factory(calendar,cash,distributions,**kwargs):
   account=Account(calendar,cash,distributions,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=cost),**kwargs);holders.append(account);return account
  try:
   case=simulation(inputs['calendar'],inputs['bars'],inputs['events'],inputs['targets'],CAPITAL,lifecycles={},account_factory=factory,policy_id=POLICY)
   validate_case(case,getattr(holders[0],'pre2026_checkpoint',None),inputs['references'][cost],inputs,cost)
   checkpoint=getattr(holders[0],'pre2026_checkpoint');artifacts=write_case(folder,case,checkpoint);cases[cost]=case;results[str(cost)]={'status':'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED','portfolio_returns_computed':False,'all676_daily_cash_share_claim_equity_checks_pass':True,'old6_financial_and_ordinaryscope_prefixes_identical':True,'old_six_serialized_prefix_sha256':prefix_artifact_hashes(case,checkpoint),'old_scope_prefix_canonical_sha256':digest(inputs['old_scope']),'artifact_sha256':artifacts}
  except (ValueError,KeyError,TypeError,ArithmeticError,OSError) as exc:results[str(cost)]=preserve_failure(folder,exc,holders,simulation,audit,case)
  write_json(out/'case_results.json',results)
 post_ok=False
 try:postcheck();post_ok=True
 except (ValueError,KeyError,TypeError,ArithmeticError,OSError) as exc:write_json(out/'source_postcheck_error.json',{'error_type':type(exc).__name__,'error':str(exc),'portfolio_returns_computed':False})
 scored=finalize_returns(results,cases,post_ok,scorer)
 if scored:
  for cost in COSTS:
   rows=[r for r in cases[cost]['days'] if r['day']>='2024-01-02'];peak=D(CAPITAL);dd=D(0)
   for r in rows:peak=max(peak,r['equity']);dd=min(dd,r['equity']/peak-1)
   results[str(cost)].update(status='CONTINUOUS_DAILY_PROXY_RECONCILED',average_exposure_pct=float(sum((r['exposure'] for r in rows),D(0))/len(rows)*100),max_drawdown_pct=float(dd*100))
 write_json(out/'case_results.json',results)
 return results,post_ok,scored

def main(argv=None):
 p=argparse.ArgumentParser()
 for k in ('source-root','repo-root','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+k,required=True)
 p.add_argument('--source-preflight-only',action='store_true');a=p.parse_args(argv);out=Path(a.output_dir);need(not out.exists(),'preserve existing account directory');need(sha(a.plan)==a.expected_plan_sha256,'external frozen account plan SHA changed')
 base,repo=Path(a.source_root),Path(a.repo_root);plan=read(a.plan);need(plan['runner_sha256']==sha(Path(__file__)),'frozen runner bytes changed');need(out.resolve()==(base/OUTPUT).resolve(),'fixed newoutput');inputs=load_inputs(base,repo,plan)
 if a.source_preflight_only:print('full source/events/old-prefix/60financial bindings verified; no account/output/returns');return 0
 def postcheck():
  need(sha(a.plan)==a.expected_plan_sha256 and sha(Path(__file__))==plan['runner_sha256'],'externalplan/runner changedduringrun');load_inputs(base,repo,plan)
 results,post_ok,scored=run_profiles(out,inputs,postcheck=postcheck)
 summary={'status':'PRICE_DELAY_CONTINUOUS_RAW_DAILY_HORIZON_DIAGNOSTIC_RECORDED','candidate':POLICY,'plan_sha256':a.expected_plan_sha256,'method_code_sha256':plan['method_code_sha256'],'raw_manifest_sha256':RAW_SHA,'event_summary_sha256':plan['event_summary_sha256'],'event_audit_sha256':plan['event_audit_sha256'],'target_sha256':TARGET_SHA,'results_by_extra_bps':results,'all60_oldfinancial_unchanged_postcheck':post_ok,'annual_returns_computed_after_both_complete_gates':scored,'execution_model':'DAILY_PROXY_ONLY','initial_CNY':CAPITAL,'reference_extra_bps':40,'annual_denominators':'2024 initial1m;2025 Dec31_2024;2026 Oct20/Dec31_2025;continuous no reset','source_queries':0,'account_price_source_projection':{'original_full_history_names':len(inputs['old_codes']),'future_only_names':len(inputs['packets'])-len(inputs['old_codes']),'future_only_pre2026_close_exception_codes':sorted(inputs['boundary_codes']),'exception_day':PRE,'exception_source_fields':['date','code','close','tradestatus','isST'],'projection_is_not_source_rewrite_or_listing_inference':True},'minute_execution_admitted':False,'original_strict_minute_admission_stays_failed':True,'full_October_2026_complete':False,'historical_arrival_verified':False,'strict_statutory_tax_certification':False,'actual_FIFO_tax_liability_verified':False,'investment_rules_changed':False,'candidate_promoted':False,'objective_achieved':False}
 write_json(out/'summary.json',summary);return 0 if scored else 2
if __name__=='__main__':raise SystemExit(main())
