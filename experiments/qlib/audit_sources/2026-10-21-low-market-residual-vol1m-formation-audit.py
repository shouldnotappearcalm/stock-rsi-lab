"""Independent stdlib-only pre2026 one-month market residual-vol formation audit.

Uses exact Decimal centered OLS on the binary-source-derived simple returns;
never imports production factors/formations or an account. --source-preflight-only
hashes the physically capped provider without reconstructing actual formations.
"""
import argparse
import copy
import hashlib
import json
import math
import re
import struct
from collections import defaultdict
from datetime import date
from decimal import Decimal as D, localcontext
from pathlib import Path

PRIMARY='low_market_residual_vol_1m';CONTROL='low_total_vol_1m_control';EQUAL='eligible_equal_weight'
START,END='2024-01-02','2025-12-31'
PROVIDER='qlib-price-delay-pre2026-clock-v2-20261021'
FORMATION='low-market-residual-vol1m-pre2026-formations-20261021'
DESIGN='docs/research/low-market-residual-vol1m-pre2026-design-2026-10-21.md'
METHODS={'scripts/prepare_low_market_residual_vol_pre2026.py','src/stock_rsi/low_market_residual_vol.py','src/stock_rsi/prior_close_orders.py','src/stock_rsi/qlib_snapshot.py','scripts/run_qlib_low_risk_pre2026.py','scripts/run_cninfo_orj_signal_pre2026.py','scripts/prepare_qlib_master_market_pre2026.py'}
MAINBOARD=re.compile(r'^(?:SH(?:600|601|603|605)|SZ(?:000|001|002|003))[0-9]{3}$')
EPS=D('1e-24')

def need(v,message):
 if not v:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def safe(root,name):
 root=Path(root).resolve();p=Path(name);need(not p.is_absolute() and '..' not in p.parts,'unsafe relative source path');p=(root/p).resolve();need(p.is_relative_to(root),'source path escaped root');return p
def positive(v):return type(v) in (int,float) and math.isfinite(v) and v>0

def previous_month(month):
 y,m=map(int,month.split('-'));return f'{y-1:04d}-12' if m==1 else f'{y:04d}-{m-1:02d}'

def month_window(calendar,execution):
 i=calendar.index(execution);need(i>0,'previous source session required');asof=calendar[i-1]
 need(execution[:7]!=asof[:7] and asof[:7]==previous_month(execution[:7]),'first execution session and previous full month required')
 days=[d for d in calendar[:i] if d[:7]==asof[:7]];j=calendar.index(days[0]);need(j>0 and calendar[j-1][:7]==previous_month(asof[:7]),'prior calendar-month baseline required')
 need(len(days)>=15,'complete month has fewer than15 observations');return asof,days,[calendar[j-1]]+days

def fit(y,x):
 need(len(y)==len(x),'OLS input shapes differ');n=len(y)
 if n<15 or not all(type(v) in (float,int) and math.isfinite(v) for v in y+x):return None
 # Decimal80 avoids adopting the production float accumulation/residual code.
 with localcontext() as context:
  context.prec=80;xd=[D.from_float(float(v)) for v in x];yd=[D.from_float(float(v)) for v in y]
  xm=sum(xd)/n;ym=sum(yd)/n;xx=sum((v-xm)**2 for v in xd)
  if xx<=EPS:return None
  xy=sum((a-xm)*(b-ym) for a,b in zip(xd,yd));beta=xy/xx;alpha=ym-beta*xm
  errors=[b-alpha-beta*a for a,b in zip(xd,yd)];sse=sum(v*v for v in errors)
  if sse<=EPS:return None
  sigma=(sse/D(n-2)).sqrt();total=(sum((v-ym)**2 for v in yd)/D(n-1)).sqrt()
  out={'n':n,'alpha':float(alpha),'beta':float(beta),'sigma':float(sigma),'sse':float(sse),'total_volatility':float(total),'market_centered_ss':float(xx)}
  return out if all(math.isfinite(v) for v in out.values()) and min(out['sigma'],out['total_volatility'])>0 else None

def simple(closes):
 need(all(positive(v) for v in closes),'missing/nonpositive close in unspliced window')
 values=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))];need(all(math.isfinite(v) for v in values),'nonfinite source return');return values

def choose(scores):
 need(len(scores)>=5 and all(positive(v) for v in scores.values()),'common eligible universe needs five positive scores')
 return sorted(scores,key=lambda code:(scores[code],code))[:len(scores)//5]

def equivalent(expected,actual,path='root'):
 if isinstance(expected,dict):
  need(isinstance(actual,dict) and set(expected)==set(actual),'field/key mismatch: '+path)
  for k,v in expected.items():equivalent(v,actual[k],path+'.'+k)
 elif isinstance(expected,list):
  need(isinstance(actual,list) and len(expected)==len(actual),'list length mismatch: '+path)
  for i,(a,b) in enumerate(zip(expected,actual)):equivalent(a,b,path+'['+str(i)+']')
 elif type(expected) is float:
  # Absolute tolerance is scaled to the field; tiny SSE cannot be replaced by0.
  absolute=1e-28 if path.endswith(('.sse','.market_centered_ss','.numeric_ss_epsilon')) else 2e-14
  need(type(actual) in (int,float) and math.isfinite(actual) and math.isclose(expected,actual,rel_tol=2e-10,abs_tol=absolute),'independent numeric mismatch: '+path)
 else:need(type(expected) is type(actual) and expected==actual,'literal/source-clock mismatch: '+path)

def authenticate(provider,repo,requestfile,requestsha):
 need(provider.name==PROVIDER,'only the fixed physical pre2026 provider is permitted');bound={}
 def auth(p,h):
  p=Path(p).resolve();need(re.fullmatch('[0-9a-f]{64}',h) is not None and sha(p)==h,'frozen source/method bytes changed: '+str(p));bound[str(p)]=h
 auth(requestfile,requestsha);request=read(requestfile)
 need(request['status']=='FROZEN_SINGLE_LOW_MARKET_RESIDUAL_VOL1M_FORMATIONS_ONLY' and request['families']==[PRIMARY] and request['descriptive_controls']==[EQUAL,CONTROL] and request['candidate_budget']==1 and request['window']==[START,END] and request['output_directory']==FORMATION,'one fixed pre2026 trial/request required')
 need(request['new_source_queries']==0 and request['portfolio_returns_to_compute'] is False and request['2026_market_values_to_query'] is False and request['new_independent_economic_family'] is False,'source-only existing-family trial boundaries changed')
 need(set(request['method_code_sha256'])==METHODS,'fixed formation method map required')
 for name,h in request['method_code_sha256'].items():auth(safe(repo,name),h)
 auth(repo/DESIGN,request['design_sha256']);auth(provider/'manifest.json',request['provider_manifest_sha256']);m=read(provider/'manifest.json')
 need(m['all_output_values_at_or_before']==END and m['output_calendar_end']==END and len(m['per_feature'])==4010,'physical quote provider cap/scope changed')
 cal=(provider/'calendars/day.txt').read_text().splitlines();need(cal and cal==sorted(set(cal)) and cal[-1]==END and all(date.fromisoformat(d).isoformat()==d and d<=END for d in cal),'pre2026 explicit quote calendar only')
 for name,meta in m['per_feature'].items():
  p=safe(provider,name);auth(p,meta['sha256']);size=p.stat().st_size;need(size>=8 and size%4==0,'bad binary source shape')
  with p.open('rb') as stream:start=struct.unpack('<f',stream.read(4))[0]
  last=int(start)+size//4-2
  need(start==int(start) and 0<=start<=last<len(cal) and meta['start_index']==int(start) and meta['last_index']==last and meta['copied_values']==size//4-1 and meta['last_date']==cal[last] and meta['last_date']<=END,'binary coordinate physically exceeds quote calendar')
 members=defaultdict(list)
 for line in (provider/'instruments/csi500.txt').read_text().splitlines():
  code,a,b=line.split();need(date.fromisoformat(a)<=date.fromisoformat(b),'historical member interval reversed')
  if MAINBOARD.fullmatch(code):members[code].append((a,b))
 codes=sorted(c for c,spans in members.items() if any(a<=END and b>='2023-12-29' for a,b in spans));need(len(codes)==501,'physical historical equity universe changed')
 files=['instruments/all.txt']+[f'features/{c.lower()}/{f}.day.bin' for c in codes for f in ('open','high','low','close','volume','factor','amount','adjclose')]+['features/sh000905/adjclose.day.bin']
 combined=hashlib.sha256()
 for name in files:
  p=safe(provider,name);content=p.read_bytes();combined.update(name.encode()+b'\0');combined.update(content);combined.update(b'\0');bound[str(p)]=hashlib.sha256(content).hexdigest()
 inputs={'price_files':combined.hexdigest()}
 for name in ('calendars/day.txt','instruments/csi500.txt','features/sh000905/close.day.bin'):
  auth(provider/name,request['input_sha256'][name]);inputs[name]=sha(provider/name)
 need(inputs==request['input_sha256']==m['output_input_sha256'],'complete price/calendar/member digest differs')
 return request,m,cal,dict(members),bound


def reconstruct(provider,calendar,members):
 """Executed only after actual output notification; every decoded scalar<=2025."""
 indices={d:i for i,d in enumerate(calendar)};cache={};latest=None
 def scalar(code,field,day,asof):
  nonlocal latest
  need(day<=asof<=END and day in indices,'future or nonexistent scalar date');latest=max(latest or day,day)
  key=(code,field)
  if key not in cache:
   p=provider/'features'/code.lower()/(field+'.day.bin');raw=p.read_bytes();values=struct.unpack('<'+'f'*(len(raw)//4),raw);start=values[0]
   need(start==int(start) and 0<=start and int(start)+len(values)-1<=len(calendar),'feature binary beyond physical cap');cache[key]=(int(start),values[1:])
  begin,values=cache[key];i=indices[day]-begin
  if not 0<=i<len(values):return None
  return values[i] if math.isfinite(values[i]) else None
 targets={k:{} for k in (PRIMARY,EQUAL,CONTROL)};receipts=[]
 executions=[d for i,d in enumerate(calendar) if START<=d<=END and i>0 and calendar[i-1][:7]!=d[:7]]
 need(len(executions)==24,'exact24 monthly executions required')
 for execution in executions:
  asof,days,close_days=month_window(calendar,execution);latest=None
  market=[scalar('SH000905','close',d,asof) for d in close_days];x=simple(market)
  with localcontext() as c:
   c.prec=80;xd=[D.from_float(v) for v in x];xm=sum(xd)/len(xd);ss=sum((v-xm)**2 for v in xd)
  need(ss>EPS,'degenerate complete-month market');marketss=float(ss)
  historical=sorted(c for c,spans in members.items() if MAINBOARD.fullmatch(c) and any(a<=asof<=b for a,b in spans))
  fits={};excluded={}
  for code in historical:
   fields={f:[scalar(code,f,d,asof) for d in close_days] for f in ('close','factor','volume')}
   invalid={f:[d for d,v in zip(close_days,values) if not positive(v)] for f,values in fields.items()};invalid={f:bad for f,bad in invalid.items() if bad}
   if invalid:excluded[code]={'reason':'incomplete_or_nonpositive_stock_fields','invalid_dates':invalid};continue
   value=fit(simple(fields['close']),x)
   if value is None:excluded[code]={'reason':'nonfinite_or_numerically_degenerate_residual'}
   else:fits[code]=value
  need(len(fits)>=5,'common eligible belowfive');scores={c:f['sigma'] for c,f in fits.items()};totals={c:f['total_volatility'] for c,f in fits.items()};selected=choose(scores);control=choose(totals)
  for name,names in [(PRIMARY,selected),(EQUAL,list(fits)),(CONTROL,control)]:targets[name][execution]={'as_of':asof,'execution_session':execution,'weights':{c:.95/len(names) for c in names}}
  need(latest==asof,'latest independent scalar read not formation cap')
  receipts.append({'execution_session':execution,'formation_asof':asof,'formation_at':asof+'T15:05:00+08:00','return_month':asof[:7],
   'sample_dates':days,'return_dates':days,'baseline_close_day':close_days[0],'close_dates':close_days,'n':len(days),'daily_return_observations':len(days),
   'minimum_return_observations':15,'minimum_n_basis':'LOCAL_COMPLETE_MONTH_CALENDAR_SOURCE_ADMISSION_PARAMETER_NOT_PAPER_RULE',
   'numeric_ss_epsilon':1e-24,'market_instrument':'SH000905','market_centered_ss':marketss,'historical_members':len(historical),'eligible':len(fits),
   'excluded':excluded,'fits':fits,'scores':scores,'selected':selected,'control_total_volatility_scores':totals,'control_selected':control,
   'controls_selectable':False,'latest_factor_price_read':latest,'primary_trial_id':PRIMARY,'trial_family':'EXISTING_LOW_RISK_LOTTERY_FAMILY_ADDITIONAL_TRIAL','model':'CSI500_MARKET_ONLY_CAPM_PROXY_NOT_FF3_REPLICATION'})
 return targets,receipts


def self_tests():
 n=20;x=[(i%5-2)/100 for i in range(n)];noise=[.003 if i<5 or 10<=i<15 else -.003 for i in range(n)];y=[.001+1.7*a+b for a,b in zip(x,noise)];f=fit(y,x)
 need(f is not None and math.isclose(f['alpha'],.001,abs_tol=1e-15) and math.isclose(f['beta'],1.7,abs_tol=1e-13) and math.isclose(f['sse'],n*.003**2,rel_tol=1e-12),'independent hand-computable OLS test')
 need(math.isclose(f['sigma'],math.sqrt(n*.003**2/(n-2)),rel_tol=1e-12),'n−2 standard error')
 need(fit(y[:14],x[:14]) is None and fit(y,[0.]*n) is None and fit([.001+1.7*a for a in x],x) is None,'n/market/zero-residual exclusions')
 scores={f'SZ00000{i}':.1 for i in range(1,7)};need(choose(scores)==['SZ000001'],'floorN5/ticker ties')
 neg={}
 def reject(label,fn):
  try:fn()
  except (ValueError,KeyError,TypeError):neg[label]=True
  else:raise AssertionError('negative not rejected: '+label)
 q={**f,'sigma':math.sqrt(f['sse']/(n-1))};reject('wrong_sigma_denominator_n_minus_1',lambda:equivalent(f,q))
 q={**f,'sigma':f['total_volatility']};reject('total_volatility_substituted_for_residual',lambda:equivalent(f,q))
 q={**f,'beta':0.};reject('omitted_market_slope',lambda:equivalent(f,q))
 q={**f,'n':19};reject('dropped_return_observation',lambda:equivalent(f,q))
 reject('underfive_quintile_pool',lambda:choose({'SZ000001':.1}))
 reject('missing_baseline_quote',lambda:simple([None,1.,1.1]))
 reject('nonfinite_quote',lambda:simple([1.,float('nan')]))
 reject('future_asof_receipt',lambda:equivalent({'formation_asof':'2023-12-29'},{'formation_asof':'2024-01-02'}))
 reject('different_member_or_target_set',lambda:equivalent({'SZ000001':.95},{'SZ000002':.95}))
 reject('nonmonthly_execution',lambda:month_window(['2023-11-30','2023-12-01','2023-12-04'],'2023-12-04'))
 return neg


def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--self-test-only',action='store_true');p.add_argument('--source-preflight-only',action='store_true')
 for n in ('provider-uri','repo-root','request','expected-request-sha256','formation-dir','output'):p.add_argument('--'+n)
 a=p.parse_args(argv);neg=self_tests()
 if a.self_test_only:print(json.dumps({'synthetic_negative_controls_rejected':neg,'actual_formations_reconstructed':False},sort_keys=True));return 0
 need(all(getattr(a,n.replace('-','_')) for n in ('provider-uri','repo-root','request','expected-request-sha256')),'explicit frozen pre2026 inputs required')
 provider=Path(a.provider_uri).resolve();repo=Path(a.repo_root).resolve();request,m,calendar,members,bound=authenticate(provider,repo,a.request,a.expected_request_sha256)
 if a.source_preflight_only:
  print('4010 physical pre2026 binary hashes/coordinates authenticated; no actual formations or ROI');return 0
 need(a.formation_dir and a.output,'actual audit needs separately notified formation directory and output')
 root=Path(a.formation_dir).resolve();need(root.name==FORMATION,'fixed new formation output only');summary=read(root/'summary.json');bound[str(root/'summary.json')]=sha(root/'summary.json')
 need(summary['status']=='LOW_MARKET_RESIDUAL_VOL1M_24_PRE2026_FORMATIONS_ONLY_NO_RETURNS' and summary['request_sha256']==a.expected_request_sha256 and summary['method_code_sha256']==request['method_code_sha256'] and summary['provider_manifest_sha256']==request['provider_manifest_sha256'] and summary['input_sha256']==request['input_sha256'],'formation summary source/request anchors')
 need(set(summary['artifact_sha256'])=={'targets.json','formation_receipts.json'},'exact formation output artifacts')
 for name,h in summary['artifact_sha256'].items():need(sha(root/name)==h,'formation output artifact changed');bound[str(root/name)]=h
 actualt=read(root/'targets.json');actualr=read(root/'formation_receipts.json');targets,receipts=reconstruct(provider,calendar,members)
 equivalent(targets,actualt);equivalent(receipts,actualr)
 need(summary['formations']==24 and summary['candidate_budget']==1 and summary['eligible_range']==[min(r['eligible'] for r in receipts),max(r['eligible'] for r in receipts)] and summary['economic_family']=='EXISTING_LOW_RISK_LOTTERY_VARIANT','summary derived count/family mismatch')
 need(summary['source_queries']==0 and summary['portfolio_returns_computed'] is False and summary['2026_market_values_queried'] is False and summary['historical_arrival_verified'] is False and summary['objective_achieved'] is False,'formation-only boundary flags')
 # Semantic output tampering controls use the actual reconstructed object shape.
 def reject(label,fn):
  try:fn()
  except (ValueError,KeyError,TypeError):neg[label]=True
  else:raise AssertionError('actual-shape mutation passed: '+label)
 q=copy.deepcopy(actualr);q[0]['fits'][next(iter(q[0]['fits']))]['sigma']*=1.01;reject('actual_fit_sigma_mutation',lambda:equivalent(receipts,q))
 q=copy.deepcopy(actualt);d=next(iter(q[PRIMARY]));c=next(iter(q[PRIMARY][d]['weights']));q[PRIMARY][d]['weights'][c]*=.99;reject('actual_target_weight_mutation',lambda:equivalent(targets,q))
 q=copy.deepcopy(actualr);q[0]['close_dates']=q[0]['close_dates'][1:];reject('actual_baseline_removed',lambda:equivalent(receipts,q))
 q=copy.deepcopy(actualr);q[0]['control_selected']=q[0]['control_selected'][1:];reject('actual_control_selection_mutation',lambda:equivalent(receipts,q))
 for name,h in bound.items():need(sha(name)==h,'source/output changed during independent audit')
 report={'status':'INDEPENDENT_LOW_MARKET_RESIDUAL_VOL1M_PRE2026_24_FORMATIONS_RECONSTRUCTED','request_sha256':a.expected_request_sha256,'summary_sha256':sha(root/'summary.json'),'audit_code_sha256':sha(__file__),
  'provider_manifest_sha256':request['provider_manifest_sha256'],'input_sha256':request['input_sha256'],'artifact_sha256':summary['artifact_sha256'],
  'formations_reconstructed':24,'all_OLS_fields_and_sample_dates_reconstructed':True,'all_primary_and_control_targets_reconstructed':True,'all_eligible_excluded_historical_members_reconstructed':True,'all4010_feature_hashes_and_physical_2025_coordinates_verified':True,
  'eligible_range':[min(r['eligible'] for r in receipts),max(r['eligible'] for r in receipts)],'sample_n_range':[min(r['n'] for r in receipts),max(r['n'] for r in receipts)],'primary_union_names':len({c for t in targets[PRIMARY].values() for c in t['weights']}),
  'first_formation_asof':receipts[0]['formation_asof'],'last_formation_asof':receipts[-1]['formation_asof'],'negative_controls_rejected':neg,'critical_or_important_findings':[],
  'imports_project_code':False,'production_factor_or_formation_called':False,'portfolio_returns_computed':False,'source_queries':0,'2026_market_values_read':False,'actual_account_replay':False,
  'limitations':['Independent Decimal80 OLS on simple returns derived from authenticated capped float32 quotes; field-scaled tolerances permit only floating arithmetic differences.','Market-only CSI500 regression, not FF3 idiosyncratic-risk replication. Same low-risk/lottery family additional trial; controls not selectable.','Price-vintage truth, historical announcement arrival, ordinary-security eligibility, raw shares, corporate actions and intraday fills are not admitted by a formation audit.']}
 out=Path(a.output);need(not out.exists(),'preserve prior independent report')
 with out.open('x') as f:json.dump(report,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
 print('independent24 pre2026 formations/OLS/common pool/controls match; no portfolio ROI');return 0

if __name__=='__main__':raise SystemExit(main())
