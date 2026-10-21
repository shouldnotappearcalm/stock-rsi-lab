"""Standalone stdlib fixed-composite target audit. No project imports/network/account.
--preflight-only reads existing pre2026 values only; full mode requires explicit output notification.
Binary file hashing is opaque. Scalar decoding is one exact as-of-bounded float at a time.
"""
import argparse,ast,copy,hashlib,json,math,re,struct,unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal
from html import unescape
from pathlib import Path
if not __debug__:raise RuntimeError('Assertions must remain enabled')
CANDIDATE='szse_value_momentum_equal'
CONTROLS=('value_leg_control','momentum_leg_control')
END='2026-10-13'
DEV='szse-value-momentum-intraday-dev-20261021'
FORM='szse-value-momentum-formations-pre2026-20261021'
DP='experiments/qlib/szse-value-momentum-intraday-plan.json'
SP='experiments/qlib/szse-value-momentum-pre2026-plan.json'
AUDIT='experiments/qlib/szse-value-momentum-intraday-ledger-audit.json'
REVIEW='experiments/qlib/szse-value-momentum-intraday-output-review.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as s:
  for b in iter(lambda:s.read(1048576),b''):h.update(b)
 return h.hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
def encoded(x):return (json.dumps(x,indent=2)+'\n').encode()
def strict(a,b):assert encoded(a)==encoded(b),'typed ordered JSON difference'
def safe(root,n):
 p=Path(n);assert not p.is_absolute() and '..' not in p.parts
 q=root/p;assert q.resolve().is_relative_to(root.resolve());return q
def plain(s):return unescape(re.sub(r'<[^>]*>','',s)).strip()
def numeric(s):
 s=unicodedata.normalize('NFKC',s).replace(',','').strip()
 if s in ('','-','--','—'):return None
 v=Decimal(s);assert v.is_finite();return str(v)
def parse_original(raw,month):
 try:html=raw.decode('utf-8-sig');encoding='utf-8-sig'
 except UnicodeDecodeError:html=raw.decode('gb18030');encoding='gb18030'
 title=re.search(r'TRANSACTIONS?\s+OF\s+SECURITIES\s*[-—]?\s*[（(]\s*(\d{4})[./-](\d{1,2})',plain(html),re.I)
 assert title and f'{int(title[1]):04d}-{int(title[2]):02d}'==month
 rows=[]
 for row in re.findall(r'<tr\b[^>]*>(.*?)</tr\s*>',html,re.I|re.S):
  cells=[]
  for c in re.finditer(r'<t[dh]\b([^>]*?)(?:/\s*>|>(.*?)</t[dh]\s*>)',row,re.I|re.S):
   cells.append((plain(c[2] or ''),c[1]))
  if cells:rows.append(cells)
 compact=lambda x:re.sub(r'\s','',unicodedata.normalize('NFKC',x))
 assert '发行量IssuedVolume10,000' in compact(rows[0][2][0])
 assert '流通量ListedVolume10,000' in compact(rows[0][3][0])
 assert '收市价Close'==compact(rows[1][7][0])
 assert '市盈率P/ERatio'==compact(rows[0][-1][0])
 stocks={};allrows=0
 for row in rows:
  code=row[0][0]
  if not re.fullmatch(r'\d{6}',code):continue
  allrows+=1
  if not code.startswith(('000','001','002','003')):continue
  assert len(row)==16
  expected=[f'c{i}' for i in range(1,9)]+['separator']+[f'c{i}' for i in range(9,16)]
  assert all(re.search(r'class=[\"\']'+re.escape(k)+r'[\"\']',attrs) for k,(_,attrs) in zip(expected,row))
  c='SZ'+code;assert c not in stocks;r=[v for v,_ in row]
  name=unicodedata.normalize('NFKC',re.sub(r'\s','',r[1])).upper()
  issued,listed,price=(numeric(r[i]) for i in (2,3,11))
  for v in (issued,listed,price):assert v is None or Decimal(v)>=0
  if issued is not None and listed is not None:assert Decimal(listed)<=Decimal(issued)
  stocks[c]={'name':r[1],'issued_10k_shares':issued,'listed_10k_shares':listed,'close':price,'pe':numeric(r[15]),'reported_special_name':'ST' in name or '退' in name}
 assert len(stocks)>=1000
 return {'month':month,'encoding':encoding,'all_security_rows':allrows,'stocks':stocks}
def month_shift(month,offset):
 y,m=map(int,month.split('-'));y,m=divmod(y*12+m-1+offset,12);return f'{y:04d}-{m+1:02d}'
def buildday(url):
 stamp=re.search(r'(?:/t|/W0)(\d{8})',url)[1];return stamp[:4]+'-'+stamp[4:6]+'-'+stamp[6:]

def field_at(code,field,day,asof):
 global latest_scalar
 assert field in ('close','factor','volume') and day<=asof<=scalar_cap
 assert day in date_indices and asof in date_indices
 key=(code,field);path=provider/'features'/code.lower()/(field+'.day.bin')
 if key not in feature_bounds:
  size=path.stat().st_size;assert size>=8 and size%4==0
  with path.open('rb') as s:begin=struct.unpack('<f',s.read(4))[0]
  assert math.isfinite(begin) and begin==int(begin) and 0<=begin<len(calendar)
  assert int(begin)+size//4-1<=len(calendar)
  feature_bounds[key]=(int(begin),size//4-1)
 begin,count=feature_bounds[key];offset=date_indices[day]-begin
 latest_scalar=max(latest_scalar,day)
 if not 0<=offset<count:return None
 with path.open('rb') as s:
  s.seek(4*(offset+1));value=struct.unpack('<f',s.read(4))[0]
 return value if math.isfinite(value) else None
def generate_formations(published):
 targets={n:{} for n in (CANDIDATE,*CONTROLS)};receipts=[]
 eligible_counts=[]
 for day in expected_execution:
  prior=calendar[date_indices[day]-1];month=month_shift(day[:7],-2);report=published[month]
  assert prior[:7]==month_shift(month,1) and max(report['article_build_day'],report['table_build_day'])<=prior
  by_month={}
  for d in calendar[:date_indices[day]]:by_month[d[:7]]=d
  ends=list(by_month.values())[-13:]
  assert len(ends)==13 and ends[-1]==prior and [d[:7] for d in ends]==[month_shift(day[:7],i) for i in range(-13,0)]
  names=sorted(c for c,spans in intervals.items() if c.startswith(('SZ000','SZ001','SZ002','SZ003')) and any(a<=prior<=b for a,b in spans))
  assert len(names)>=100;covered=[c for c in names if c in report['stocks']];assert len(covered)>=.95*len(names)
  pes={};momentum={};excluded={}
  for c in covered:
   r=report['stocks'][c]
   if r['reported_special_name'] or r['pe'] is None:excluded[c]='SPECIAL_PUBLISHED_NAME_OR_MISSING_PE';continue
   pe=Decimal(r['pe']);assert pe.is_finite()
   if pe<=0:excluded[c]='NONPOSITIVE_PUBLISHED_PE';continue
   current=[field_at(c,f,prior,prior) for f in ('close','factor','volume')]
   if any(v is None or v<=0 for v in current):excluded[c]='MISSING_OR_INACTIVE_FORMATION';continue
   prices=[field_at(c,'close',d,prior) for d in ends]
   if any(v is None or v<=0 for v in prices):excluded[c]='INCOMPLETE_13_MONTH_HISTORY';continue
   score=prices[11]/prices[0]-1
   assert math.isfinite(score);pes[c]=pe;momentum[c]=score
  assert len(pes)>=50 and len(pes)>=.5*len(names);eligible_counts.append(len(pes))
  n=len(pes)//10;value_names=sorted(pes,key=lambda c:(pes[c],c))[:n];momentum_names=sorted(momentum,key=lambda c:(-momentum[c],c))[:n]
  expected={'execution_session':day,'formation_asof':prior,'source_month':month,'source_article_build_day':report['article_build_day'],'source_table_build_day':report['table_build_day'],
   'source_table_sha256':report['table_sha256'],'availability_convention':'complete following trading month ends at formation close','historical_arrival_verified':False,
   'historical_members':len(names),'published_member_rows':len(covered),'eligible':len(pes),'excluded':excluded,'published_pe':{c:str(v) for c,v in pes.items()},'momentum_scores':momentum,
   'month_end_price_dates':ends,'ranking_return_months':[d[:7] for d in ends[1:-1]],'skipped_ranking_month':ends[-1][:7],
   'value_selected':value_names,'momentum_selected':momentum_names,'overlap_names':sorted(set(value_names)&set(momentum_names)),
   'sleeve_capital_budgets':{'value':.475,'momentum':.475},'latest_factor_price_read':prior}
  receipts.append(expected)
  weights={c:math.fsum((.475/len(value_names) if c in value_names else 0.,.475/len(momentum_names) if c in momentum_names else 0.)) for c in sorted(set(value_names)|set(momentum_names))}
  targets[CANDIDATE][day]={'as_of':prior,'weights':weights}
  assert math.isclose(math.fsum(weights.values()),.95,abs_tol=1e-14)
  for family,selected in zip(CONTROLS,(value_names,momentum_names)):
   targets[family][day]={'as_of':prior,'weights':{c:.95/len(selected) for c in selected}}
 return targets,receipts,eligible_counts

def cap_only(repo,newtext=None):
 old=ast.parse((repo/'src/stock_rsi/exchange_value_momentum.py').read_text())
 new=ast.parse(newtext if newtext is not None else (repo/'src/stock_rsi/exchange_value_momentum_extended.py').read_text())
 ob=next(x for x in old.body if isinstance(x,ast.FunctionDef) and x.name=='build_targets')
 nb=next(x for x in new.body if isinstance(x,ast.FunctionDef) and x.name=='build_targets')
 # Normalize exactly the new explicit permission argument and its one guard use.
 assert len(nb.args.kwonlyargs)==1 and nb.args.kwonlyargs[0].arg=='permitted_end'
 assert ast.dump(nb.args.kw_defaults[0])==ast.dump(ast.Name(id='END',ctx=ast.Load()))
 nb.args.kwonlyargs=[];nb.args.kw_defaults=[]
 guard=nb.body[0];oldguard=ob.body[0]
 assert isinstance(guard,ast.If) and len(guard.body)==1 and isinstance(guard.body[0],ast.Raise)
 assert ast.dump(guard.test)==ast.dump(ast.parse('start<START or start>end or end>permitted_end',mode='eval').body)
 assert ast.dump(guard.body[0])==ast.dump(ast.parse("raise ValueError('value/momentum exceeds explicit date permission')").body[0])
 nb.body[0]=copy.deepcopy(oldguard)
 assert ast.dump(old)==ast.dump(new),'economic AST differs beyond two permission edits'
 return True

def memberships(path):
 result=defaultdict(list)
 for line in path.read_text().splitlines():
  c,a,b=line.split();assert date.fromisoformat(a)<=date.fromisoformat(b)
  if c.startswith(('SH600','SH601','SH603','SH605','SZ000','SZ001','SZ002','SZ003')):result[c].append((a,b))
 return result

def provider_hashes(provider):
 spans=memberships(provider/'instruments/csi500.txt')
 codes=sorted(c for c,periods in spans.items() if any(a<=END and b>='2023-12-29' for a,b in periods))
 files=[Path('instruments/all.txt')]
 for c in codes:files.extend(Path('features')/c.lower()/(f+'.day.bin') for f in ('open','high','low','close','volume','factor','amount','adjclose'))
 files.append(Path('features/sh000905/adjclose.day.bin'));h=hashlib.sha256()
 for f in files:
  h.update(f.as_posix().encode()+b'\0')
  with (provider/f).open('rb') as s:
   for chunk in iter(lambda:s.read(1048576),b''):h.update(chunk)
  h.update(b'\0')
 return {'price_files':h.hexdigest(),**{n:sha(provider/n) for n in ('instruments/csi500.txt','calendars/day.txt','features/sh000905/close.day.bin')}}

def authenticate(base,repo,p,planfile,expected):
 assert sha(planfile)==expected
 assert p['status']=='FROZEN_COMPOSITE_2026_TARGET_EXTENSION_V2_SOURCE_CALENDAR_GUARD' and p['candidate']==CANDIDATE and p['candidate_budget']==1
 assert p['target_end']==END and p['planned_account_end']=='2026-10-20' and p['full_October_complete'] is False
 assert p['provider_relative']=='qlib-enhanced-2026-diagnostic' and p['output_relative']=='szse-value-momentum-formations-full-v2-20261021'
 for flag in ('new_2026_strategy_returns_allowed','controls_selectable','historical_arrival_verified','sealed_evidence','objective_achieved'):assert p[flag] is False
 assert p['network_calls_permitted']==0 and p['new_2026_features_read_before_freeze'] is True and p['investment_rules_changed'] is False
 assert sha(repo/'experiments/qlib/szse-value-momentum-2026-target-plan.json')==p['v1_plan_sha256']
 failurefile=repo/'experiments/qlib/szse-value-momentum-2026-target-v1-failure.json';failure=load(failurefile)
 assert sha(failurefile)==p['v1_failure_sha256'] and failure['plan_sha256']==p['v1_plan_sha256']
 assert failure['original_script_sha256']==sha(repo/'scripts/prepare_value_momentum_2026_targets.py')
 assert failure['actual_exit_code']==1 and failure['original_output_created'] is False
 assert failure['new_2026_factor_features_read'] is True and failure['2026_strategy_returns_computed'] is False
 assert failure['account_replay_performed'] is False and failure['investment_code_changed'] is False
 assert failure['log_sha256']==sha(repo/'experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-target-v1-failure.log')
 bound={}
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for n,h in p[field].items():
   f=safe(parent,n);assert sha(f)==h,n;bound[f]=h
 for name in (DP,SP):
  for n,h in load(repo/name)['method_code_sha256'].items():assert sha(safe(repo,n))==h
 s=load(base/DEV/'summary.json');audit=load(repo/AUDIT);review=load(repo/REVIEW)
 assert s['status']=='FIXED_COMPOSITE_PRE2026_INTRADAY_DEVELOPMENT_COMPLETE' and s['candidate']==CANDIDATE
 assert s['window']==['2023-12-29','2025-12-31'] and s['raw_development_confirmation_passes'] is True
 assert s['plan_sha256']==sha(repo/DP) and s['method_code_sha256']==load(repo/DP)['method_code_sha256']
 assert sha(base/DEV/'summary.json')==sha(repo/'experiments/qlib/szse-value-momentum-intraday-results.json')==audit['summary_sha256']==review['summary_sha256']
 for f in ('development_confirmation_passes_independently','all_profile_parent_child_fill_quantities_and_snapshots_reconstructed'):assert audit[f] is True
 assert audit['imports_project_code'] is False and audit['2026_return_computed'] is False and s['2026_strategy_returns_queried'] is False
 assert audit['arithmetic_negative_controls_rejected'] and all(audit['arithmetic_negative_controls_rejected'].values())
 assert audit['audit_code_sha256']==sha(repo/'experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-intraday-audit.py')
 assert audit['plan_sha256']==review['plan_sha256']==sha(repo/DP)
 assert review['ready_for_frozen_2026_source_extension'] is True and review['no2026read'] is True and review['independent_audit_sha256']==sha(repo/AUDIT)
 assert set(s['results_by_profile'])==set(audit['results_by_profile'])=={f'{x}/{c}' for x in (100,500,1000) for c in (20,40)}
 count=0
 for label,r in s['results_by_profile'].items():
  assert r['status']=='NESTED_EXECUTION_ACCOUNT_RECONCILED'
  assert set(r['artifact_sha256'])=={'daily.csv','intents.json','parent_instructions.json','orders.json','fills.json','corporate_ledger.json','ownership.json'}
  for n,h in r['artifact_sha256'].items():
   assert Path(n).name==n;f=safe(base/DEV/label,n);assert sha(f)==h;bound[f]=h;count+=1
 assert count==42;cap_only(repo)
 assert provider_hashes(base/p['provider_relative'])==p['input_sha256']
 return bound

def source_reports(base,repo,relative,expected_hash,months):
 root=base/relative;assert sha(root/'manifest.json')==expected_hash
 m=load(root/'manifest.json')
 status='PRE2026_SZSE_MONTHLY_ORIGINAL_TABLES_CAPTURED' if relative=='szse-monthly-pre2026-20261017' else 'SZSE_MONTHLY_2026_EXTENSION_ORIGINAL_TABLES_CAPTURED'
 assert m['status']==status and m['source_reader_sha256']==sha(repo/'src/stock_rsi/szse_monthly.py')
 assert sha(root/'request.json')==m['request_sha256'] and set(m['months'])==set(months)
 for n,h in m['journal_artifact_sha256'].items():assert sha(safe(root,n))==h
 result={}
 for month,item in m['months'].items():
  for kind in ('article','table','normalized'):assert sha(safe(root,item[kind+'_file']))==item[kind+'_sha256']
  for receipt in item.get('query_receipts',[]):
   for kind in ('request','reserved','response'):assert sha(safe(root,receipt[kind+'_file']))==receipt[kind+'_sha256']
  parsed=parse_original(safe(root,item['table_file']).read_bytes(),month);norm=load(safe(root,item['normalized_file']))
  assert all(norm[k]==v for k,v in parsed.items())
  assert norm['article_build_day']==buildday(item['article_url']) and norm['table_build_day']==buildday(item['table_url'])
  result[month]={**parsed,'article_build_day':norm['article_build_day'],'table_build_day':norm['table_build_day'],'table_sha256':item['table_sha256']}
 return result

def monthly_days(days,start,end):
 assert days and days==sorted(set(days))
 return [d for i,d in enumerate(days) if start<=d<=end and i>0 and d[:7]!=days[i-1][:7]]

def setup_market(root,cap):
 global provider,calendar,date_indices,intervals,feature_bounds,latest_scalar,scalar_cap,expected_execution
 provider=root;calendar=(provider/'calendars/day.txt').read_text().splitlines()
 assert calendar==sorted(set(calendar)) and calendar[-1]==END
 assert all(date.fromisoformat(d).isoformat()==d for d in calendar)
 date_indices={d:i for i,d in enumerate(calendar)};intervals=memberships(provider/'instruments/csi500.txt')
 scalar_cap=cap;feature_bounds={};latest_scalar=''
 expected_execution=monthly_days(calendar,'2024-01-02',cap)

def verify_prefix(base,targets,receipts):
 prior={n:{d:t for d,t in v.items() if d<'2026-01-01'} for n,v in targets.items()}
 oldreceipts=[r for r in receipts if r['execution_session']<'2026-01-01']
 assert len(oldreceipts)==24 and encoded(prior)==(base/FORM/'targets.json').read_bytes()
 assert encoded(oldreceipts)==(base/FORM/'formation_receipts.json').read_bytes()
 return True

def negative_controls(repo,published,targets,receipts):
 negative={}
 for first in ('2026-10-08','2026-10-09'):
  assert monthly_days(['2026-09-30',first,'2026-10-12'],'2026-01-01',END)==[first]
 def rejects(name,fn):
  try:fn()
  except (AssertionError,ValueError,KeyError):negative[name]=True
  else:raise AssertionError('semantic mutation accepted: '+name)
 day=expected_execution[-1];prior=calendar[date_indices[day]-1]
 rejects('future_scalar_beyond_formation',lambda:field_at('SZ000001','close',day,prior))
 rejects('scalar_beyond_explicit_cap',lambda:field_at('SZ000001','close',calendar[-1],'2026-10-14'))
 for name,change in (
  ('altered_momentum_score',lambda t,r:r[-1]['momentum_scores'].__setitem__(next(iter(r[-1]['momentum_scores'])),123456.)),
  ('one_month_source_lag',lambda t,r:r[-1].__setitem__('source_month',month_shift(day[:7],-1))),
  ('wrong_skip_latest_month',lambda t,r:r[-1].__setitem__('skipped_ranking_month',r[-1]['ranking_return_months'][-1])),
  ('wrong_historical_member_count',lambda t,r:r[-1].__setitem__('historical_members',r[-1]['historical_members']+1)),
  ('lost_overlap_budget',lambda t,r:t[CANDIDATE][day]['weights'].__setitem__(next(iter(t[CANDIDATE][day]['weights'])),0.)),
  ('control_replaces_candidate',lambda t,r:t.__setitem__(CANDIDATE,copy.deepcopy(t[CONTROLS[0]]))),
  ('missing_month',lambda t,r:r.pop()),
  ('false_arrival_certification',lambda t,r:r[-1].__setitem__('historical_arrival_verified',True))):
  t=copy.deepcopy(targets);r=copy.deepcopy(receipts);change(t,r)
  rejects(name,lambda t=t,r=r:strict([t,r],[targets,receipts]))
 original=(repo/'src/stock_rsi/exchange_value_momentum_extended.py').read_text()
 rejects('economic_AST_weight_change',lambda:cap_only(repo,original.replace('.475','.476')))
 rejects('economic_AST_momentum_endpoint_change',lambda:cap_only(repo,original.replace('closes[-2]','closes[-1]')))
 altered=copy.deepcopy(published);altered[receipts[-1]['source_month']]['table_build_day']=day
 rejects('source_not_available_before_formation',lambda:generate_formations(altered))
 return negative

def main():
 ap=argparse.ArgumentParser()
 for n in ('source-root','repo-root','plan','expected-plan-sha256'):ap.add_argument('--'+n,required=True)
 ap.add_argument('--target-dir');ap.add_argument('--output');ap.add_argument('--preflight-only',action='store_true');a=ap.parse_args()
 base=Path(a.source_root);repo=Path(a.repo_root);planfile=Path(a.plan);p=load(planfile)
 if a.output:assert not Path(a.output).exists(),'preserve first report'
 bound=authenticate(base,repo,p,planfile,a.expected_plan_sha256)
 # This old source is safe for preparation: no extension monthly values are opened here.
 published=source_reports(base,repo,'szse-monthly-pre2026-20261017',p['development_monthly_manifest_sha256'],[month_shift('2023-11',i) for i in range(24)])
 setup_market(base/p['provider_relative'],'2025-12-31' if a.preflight_only else END)
 if a.preflight_only:
  assert len(expected_execution)==24
 else:
  assert a.target_dir and a.output
  root=Path(a.target_dir);assert root.resolve()==(base/p['output_relative']).resolve()
  extra=source_reports(base,repo,'szse-monthly-2026-extension-20261017',p['extension_monthly_manifest_sha256'],[month_shift('2025-11',i) for i in range(10)])
  assert not set(published)&set(extra);published.update(extra)
  assert len(expected_execution)==34 and expected_execution[-1][:7]=='2026-10'
 targets,receipts,eligible=generate_formations(published);verify_prefix(base,targets,receipts)
 negatives=negative_controls(repo,published,targets,receipts)
 if a.preflight_only:
  assert latest_scalar<='2025-12-31'
  print('Preflight passed: AST cap-only, immutable input hashes, six old accounts/42 files, 24 original signal receipts/targets and semantic negatives. No new2026 values/output opened.')
 else:
  actualtargets=load(root/'family_targets.json');actualreceipts=load(root/'formation_receipts.json');strict(actualtargets,targets);strict(actualreceipts,receipts)
  strict(load(root/'targets.json'),targets[CANDIDATE])
  # Exact serialized bytes also bind ordering and full original prefix, not just parsed equality.
  assert (root/'family_targets.json').read_bytes()==encoded(targets) and (root/'formation_receipts.json').read_bytes()==encoded(receipts)
  assert (root/'targets.json').read_bytes()==encoded(targets[CANDIDATE])
  receipt=load(root/'receipt.json')
  artifacts={n:sha(root/n) for n in ('family_targets.json','formation_receipts.json','targets.json')}
  expected={'status':'FIXED_COMPOSITE_2026_TARGETS_PREPARED_NO_RETURNS_V2','candidate':CANDIDATE,'candidate_budget':1,'plan_sha256':sha(planfile),'months':34,
   'target_generation_calendar_end':END,'latest_target_execution_session':expected_execution[-1],'source_calendar_monthly_sessions_verified':True,'v1_failure_preserved':True,'planned_interim_account_end':'2026-10-20',
   'requested_full_October_complete':False,'development_targets_and_receipts_prefix_reproduced':True,'permission_only_source_change_verified':True,'controls_promoted':False,
   'artifact_sha256':artifacts,'input_sha256':p['input_sha256'],'new_2026_factor_features_read':True,'2026_strategy_returns_queried':False,
   'account_replay_performed':False,'historical_arrival_verified':False,'sealed_evidence':False,'objective_achieved':False}
  # Input/output key order in manifest artifact map is immaterial, types and values are exact.
  assert json.dumps(receipt,sort_keys=True)==json.dumps(expected,sort_keys=True)
  assert set(f.name for f in root.iterdir())=={*artifacts,'receipt.json'}
  result={'status':'INDEPENDENT34_FIXED_COMPOSITE_TARGETS_AND_COMPLETE_FORMATION_RECEIPTS_RECONSTRUCTED','audit_code_sha256':sha(__file__),
   'plan_sha256':sha(planfile),'receipt_sha256':sha(root/'receipt.json'),'artifact_sha256':artifacts,
   'all34_original_HTML_PE_rankings_common_universes_momentum_scores_overlaps_and_receipts_reconstructed':True,
   'all_three_families_34_targets_reconstructed':True,'original24_complete_receipts_and_family_targets_byte_exact':True,
   'six_original_accounts_and42_financial_artifacts_unchanged':True,'v1_failure_preserved':True,'v1_new2026_factor_read_disclosed':True,'AST_only_explicit_date_permission':True,'all34_execution_identities_and_previous_session_asofs_derived_from_source_calendar':True,
   'target_count':34,'latest_target':expected_execution[-1],'latest_factor_scalar_decoded':latest_scalar,'minimum_common_eligible':min(eligible),
   'candidate_union_names':len({c for t in targets[CANDIDATE].values() for c in t['weights']}),'semantic_negative_controls_rejected':negatives,
   'negative_controls_use_hash_gate':False,'imports_project_code':False,'source_queries_performed':0,'account_replay_performed':False,
   'portfolio_returns_computed':False,'2026_strategy_returns_read':False,'controls_promoted':False,'historical_arrival_verified':False,'sealed_evidence':False,'objective_achieved':False,
   'limitations':['Source filename/build dates and full following-month lag do not authenticate historical arrival.',
    'Published positivePE and normalized Qlib scalar reconstruction do not certify earnings vintage, raw corporate entitlements, execution, or account returns.',
    'Calendar ends October13; October execution day is derived from the source calendar and formed at the preceding month end. No complete October account result is established.']}
 for f,h in bound.items():assert sha(f)==h
 assert provider_hashes(base/p['provider_relative'])==p['input_sha256'] and sha(planfile)==a.expected_plan_sha256
 if not a.preflight_only:
  with Path(a.output).open('x') as s:json.dump(result,s,indent=2);s.write('\n')
  print('Independent34 fixed-composite signals/all family targets and24month byte prefix verified; no account/network/ROI')
 return 0
if __name__=='__main__':raise SystemExit(main())
