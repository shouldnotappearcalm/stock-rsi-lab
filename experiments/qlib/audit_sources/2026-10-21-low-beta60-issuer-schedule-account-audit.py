"""Stdlib output auditor; daily conservation only, no aggregate period return calculation.
Adapted from the frozen development auditor; no project code is imported or executed.
The source evidence/admission auditors are authenticated trust roots, not legal proof.
"""
import argparse,copy,csv,hashlib,json,sys
from collections import defaultdict
from datetime import datetime,timedelta
from decimal import Decimal as D,ROUND_HALF_UP,ROUND_DOWN,ROUND_UP
from pathlib import Path
from zoneinfo import ZoneInfo
if not __debug__:raise RuntimeError('audit assertions require ordinary Python, without -O')
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
read=lambda f:json.loads(Path(f).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def cents(v):return v.quantize(D('.01'),rounding=ROUND_HALF_UP)
def at(day,clock):return datetime.fromisoformat(day+'T'+clock+'+08:00').astimezone(ZoneInfo('UTC')).isoformat()
def localday(ts):return datetime.fromisoformat(ts).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
def bindings(plan,scopes):
 for field,parent in scopes:
  for name,h in plan[field].items():
   assert not Path(name).is_absolute() and '..' not in Path(name).parts
   assert sha(parent/name)==h,(field,name)
def artifacts(root,declared):
 for name,h in declared.items():
  assert Path(name).name==name and sha(root/name)==h,name
CLASSIFICATION='ISSUER_FORMAL_TAX_SCHEDULE_COMPOSITE_INFERENCE'
PROFILES={f'{p}/{e}' for p in (100,500,1000) for e in (20,40)}
ARTIFACTS={'rows':'daily.csv','intents':'intents.json','parent_instructions':'parent_instructions.json','orders':'orders.json','fills':'fills.json','corporate_ledger':'corporate_ledger.json','ownership':'ownership.json'}
CLOCKS={'rows':'day','intents':'execution_session','parent_instructions':'eligible_at','orders':'submitted_at','fills':'execution_at','corporate_ledger':'day'}
def table(path):
 with path.open() as stream:return list(csv.DictReader(stream))
def prefix_checks(v,profile):
 prior=development_summary['results_by_profile'][profile];folder=development/profile
 assert set(prior['artifact_sha256'])==set(ARTIFACTS.values());artifacts(folder,prior['artifact_sha256'])
 for key,name in ARTIFACTS.items():
  old=table(folder/name) if key=='rows' else read(folder/name)
  actual={d:x for d,x in v[key].items() if d<'2026-01-01'} if key=='ownership' else [x for x in v[key] if x[CLOCKS[key]]<'2026-01-01']
  assert old==actual,(profile,'pre2026 prefix',name)
 failed=failure_states[profile]
 for key,oldkey in (('parent_instructions','parent_instructions'),('orders','child_orders'),('fills','fills'),('corporate_ledger','corporate_ledger')):
  assert [x for x in v[key] if x[CLOCKS[key]]<'2026-06-17']==failed[oldkey],(profile,'strict failure ledger prefix',key)
 return 7

def tape(code,day):
 key=(code,day);name=code+'-'+day+'.json';assert day<='2026-10-20' and key in tape_index
 f,h=tape_index[key];assert sha(f)==h
 if key in tape_cache:return tape_cache[key]
 packet=read(f);assert packet['instrument']==code and packet['requested_day']==day
 points=packet.get('methods',{}).get('minutes.history',packet)['response']['points'];assert len(points)==240
 windows=[]
 for n in range(0,240,5):
  block=points[n:n+5];end=datetime.fromisoformat(block[-1]['time']).astimezone(ZoneInfo('UTC'));start=end-timedelta(minutes=5)
  prices=[D(x['price_milli'])/1000 for x in block if x['volume']>0]
  windows.append({'start':start.isoformat(),'end':end.isoformat(),'volume':sum(max(0,x['volume']*100-100) for x in block),
   'buy':max(prices) if prices else None,'sell':min(prices) if prices else None,
   'evidence':digest({'security_id':code,'day':day,'points':[{'time':x['time'],'volume':x['volume'],'price_milli':x['price_milli']} for x in block]})})
 assert sum(w['volume'] for w in windows)<=D(bars[code][day]['volume'])
 tape_cache[key]=windows;return windows

def legal_quantity(remaining,capacity,side):
 cap=min(remaining,capacity,1000000)
 return remaining if side=='SELL' and remaining<=cap else cap//100*100

def fee(gross,side,extra):return cents(max(D(5),gross*D('.0005' if side=='BUY' else '.0015')))+cents(gross*D(extra)/10000)
def load_case(folder,stated):
 assert stated['status']=='CONDITIONAL_ENGINEERING_ACCOUNT_COMPLETE_UNSCORED'
 assert set(stated['artifact_sha256'])=={'daily.csv','orders.json','fills.json','corporate_ledger.json','ownership.json','intents.json','parent_instructions.json','scenario_ledger.json'}
 assert stated['portfolio_returns_computed'] is False and stated['source_events_changed'] is False and stated['statutory_exemption_verified'] is False
 for f,h in stated['artifact_sha256'].items():assert sha(folder/f)==h
 v={n:read(folder/(n+'.json')) for n in ('orders','fills','corporate_ledger','ownership','intents','parent_instructions','scenario_ledger')}
 with (folder/'daily.csv').open() as stream:v['rows']=list(csv.DictReader(stream))
 return v

def audit(v,participation,extra,stated):
 rows=v['rows'];orders=v['orders'];fills=v['fills'];ledger=v['corporate_ledger'];ownership=v['ownership'];intents=v['intents'];parents=v['parent_instructions']
 assert [r['day'] for r in rows]==sessions and set(ownership)==set(sessions)
 assert len(intents)==34 and len({i['execution_session'] for i in intents})==34
 by_intent={localday(i['as_of']):i for i in intents};assert len(by_intent)==34
 by_order=defaultdict(list);by_ledger=defaultdict(list);by_fill=defaultdict(list)
 for o in parents:by_order[localday(o['eligible_at'])].append(o)
 for x in ledger:by_ledger[x['day']].append(x)
 for f in fills:by_fill[localday(f['execution_at'])].append(f)
 assert set(by_order)<=set(sessions) and set(by_ledger)<=set(sessions) and set(by_fill)<=set(sessions)
 omap={o['order_id']:o for o in orders};assert len(omap)==len(orders)
 pmap={p['order_id']:p for p in parents};assert len(pmap)==len(parents)
 expected_parents={}
 for intent in intents:
  assert intent['as_of']==at(localday(intent['as_of']),'15:05:00')
  dids=[digest({'decision':d,'snapshot':intent['snapshot_sha256']}) for d in intent['decisions']]
  batch=digest({'decisions':dids,'at':intent['as_of'],'participation':participation,'extra':str(D(extra)/10000)})
  for d,did in zip(intent['decisions'],dids):
   key=digest({'batch':batch,'decision':did,'role':'intraday_parent'})
   assert key not in expected_parents
   expected_parents[key]={'order_id':key,'decision_id':did,'submitted_at':intent['as_of'],
    'eligible_at':at(intent['execution_session'],'09:30:00'),'expires_at':at(intent['execution_session'],'14:55:00'),
    'legacy_expiry_hint':at(intent['execution_session'],'09:30:00'),'order_role':'PARENT_EXECUTION_INSTRUCTION_NOT_EXCHANGE_ORDER',
    **{k:d[k] for k in ('action','security_id','quantity')}}
 assert set(pmap)==set(expected_parents)
 for key,parent in pmap.items():
  assert {k:parent[k] for k in expected_parents[key]}==expected_parents[key]
  assert type(parent['quantity']) is int and parent['quantity']>0
 fmap={f['order_id']:f for f in fills};assert len(fmap)==len(fills) and set(fmap)<=set(omap)
 expected_all_children=[]
 cash=D('1000000');previous=cash;lots=defaultdict(list);marks={};claims={};stockclaims={};registered={};nav={}
 total_fees=D(0);extra_fees=D(0);gross_div=D(0);tax=D(0);capacity=D(0);count=0;filled_seen=set();snapshot_count=0
 expected_scenario=[];cash_history=[];stock_history=[]
 for index,row in enumerate(rows):
  day=row['day'];entries=by_ledger[day];expected_ledger=[];dayfees=D(0);paid=D(0)
  for eid,(available,net) in list(claims.items()):
   if available==day:
    expected_ledger.append({'day':day,'kind':'NET_DIVIDEND_CASH_AVAILABLE','event_id':eid,'cash_delta':str(net)})
    cash+=net;paid+=net;del claims[eid]
    next(c for c in cash_history if c['event_id']==eid)['paid']=True
  for eid,e in events.items():
   if e['ex_date']!=day:continue
   q=registered[eid];gross=cents(D(e['cash_per_share'])*q);income=cents(D(e['stock_taxable_income_per_share'])*q)
   reserve=cents((gross+income)*D('.2'));cap=D(e['capital_per_share'])*q;stock=D(e['stock_per_share'])*q
   assert cap==int(cap) and stock==int(stock) and reserve<=gross
   assert not q or not cap or e['capital_tax_exempt_verified'] is True or e==registry['event']
   if q and e==registry['event']:
    expected_scenario.append({'day':day,'event_id':eid,'classification':CLASSIFICATION,'registered_quantity':q,'capital_shares':int(cap),'cash_gross':str(gross),'stress_tax_reserve':str(reserve),'statutory_exemption_verified':False,'original_strict_flag':False,'registry_semantic_sha256':digest(registry)})
   assert not q or not stock or e['stock_tax_basis_verified'] is True
   if gross:
    available=next((s for s in sessions if s>e['pay_date']),None);claims[eid]=(available,gross-reserve)
    cash_history.append({'event_id':eid,'instrument':e['instrument'],'gross':str(gross),'reserve':str(reserve),'net':str(gross-reserve),'available_on':available,'paid':False})
   for amount,kind in ((int(cap),'CAPITAL_SHARES_LISTED'),(int(stock),'STOCK_DIVIDEND_SHARES_LISTED')):
    if amount:
     stockclaims[(eid,kind)]=(e['instrument'],amount,e['listed'],e['recorded'])
     stock_history.append({'event_id':eid,'instrument':e['instrument'],'quantity':amount,'listed':e['listed'],'recorded':e['recorded'],'credited':False,'share_kind':'CAPITAL_TRANSFER' if kind=='CAPITAL_SHARES_LISTED' else 'STOCK_DIVIDEND'})
   expected_ledger.append({'day':day,'kind':'EX_DATE_ENTITLEMENT','event_id':eid,'instrument':e['instrument'],
    'registered_quantity':q,'cash_gross':str(gross),'stress_tax_reserve':str(reserve),
    'capital_shares':int(cap),'stock_shares':int(stock),'taxable_stock_income':str(income)})
   gross_div+=gross;tax+=reserve
  for key,(code,q,listed,recorded) in list(stockclaims.items()):
   if listed<=day:
    lots[code].append([q,recorded,D(0)]);del stockclaims[key]
    next(c for c in stock_history if c['event_id']==key[0] and c['share_kind']==('CAPITAL_TRANSFER' if key[1]=='CAPITAL_SHARES_LISTED' else 'STOCK_DIVIDEND'))['credited']=True
    expected_ledger.append({'day':day,'kind':key[1],'event_id':key[0],'quantity':q})
  seen_day=[];states={}
  for parent in by_order[day]:
   c=parent['security_id'];assert bars[c][day]['isST']=='0'
   states[parent['order_id']]={'remaining':parent['quantity'],'filled_quantity':0,
    'status':'UNFILLED_HALTED_DAY' if bars[c][day]['tradestatus']=='0' else 'PENDING'}
  for window_index in range(1,47):
   active=[parent for parent in by_order[day] if states[parent['order_id']]['status']=='PENDING']
   if not active:break
   children=[];budget=cash
   for parent in sorted(active,key=lambda p:(p['action']!='SELL',p['security_id'])):
    c=parent['security_id'];side=parent['action'];remaining=states[parent['order_id']]['remaining'];series=tape(c,day);prev,current=series[window_index-1:window_index+1]
    cap=prev['volume']*participation//10000
    if side=='SELL':cap=min(cap,sum(q for q,bought,_ in lots[c] if bought<day))
    q=legal_quantity(remaining,cap,side)
    limit=(D(bars[c][day]['preclose'])*D('1.095' if side=='BUY' else '.905')).quantize(D('.01'),rounding=ROUND_DOWN if side=='BUY' else ROUND_UP)
    if side=='BUY':
     q=min(q,int(budget/limit)//100*100)
     while q and limit*q+fee(limit*q,side,extra)>budget:q-=100
    if not q:continue
    reserve=limit*q+fee(limit*q,side,extra) if side=='BUY' else D(0)
    if side=='BUY':budget-=reserve
    key=digest({'parent':parent['order_id'],'start':current['start'],'end':current['end'],'quantity':q,'previous_volume':prev['volume'],'evidence_id':prev['evidence']})
    expected_child={'order_id':key,'parent_id':parent['order_id'],'security_id':c,'action':side,'quantity':q,
     'limit_price':str(limit),'submitted_at':current['start'],'expires_at':current['end'],'status':'PENDING','filled_quantity':0,
     'order_role':'EXPLICIT_CHILD_ORDER','source_volume_as_of':prev['end'],'source_volume_lower_shares':prev['volume'],
     'source_evidence_id':prev['evidence'],'reserved_cash':str(reserve)}
    children.append(expected_child)
   assert budget>=0
   for child in sorted(children,key=lambda c:(c['action']!='BUY',c['security_id'])):
    c=child['security_id'];side=child['action'];state=states[child['parent_id']];current=tape(c,day)[window_index]
    q=legal_quantity(min(state['remaining'],child['quantity']),current['volume']*participation//10000,side)
    price=current['buy' if side=='BUY' else 'sell'];limit=D(child['limit_price'])
    if not q or price is None or side=='BUY' and price>=limit or side=='SELL' and price<=limit:
     child['status']='UNFILLED_VOLUME_OR_PRICE';continue
    if side=='SELL':assert q<=sum(n for n,bought,_ in lots[c] if bought<day)
    gross=price*q;cost=fee(gross,side,extra)
    if side=='SELL' and cash+gross<cost:child['status']='UNFILLED_FEES_CASH';continue
    if side=='BUY':
     assert gross+cost<=D(child['reserved_cash']) and gross+cost<=cash
     cash-=gross+cost;lots[c].append([q,day,price])
    else:
     cash+=gross-cost;left=q
     for lot in lots[c]:
      if lot[1]<day:take=min(left,lot[0]);lot[0]-=take;left-=take
     assert left==0
    lots={code:[ls for ls in items if ls[0]] for code,items in lots.items()};lots=defaultdict(list,{code:ls for code,ls in lots.items() if ls})
    state['remaining']-=q;state['filled_quantity']+=q
    if not state['remaining']:state['status']='FILLED'
    child.update(status='FILLED' if q==child['quantity'] else 'PARTIAL_WINDOW_EXPIRED',filled_quantity=q)
    expected_fill={'order_id':child['order_id'],'parent_id':child['parent_id'],'execution_at':current['end'],
     'security_id':c,'action':side,'quantity':q,'price':str(price),'cost':str(cost),'cash_after':str(cash),
     'current_volume_lower_shares':current['volume'],'current_evidence_id':current['evidence']}
    assert expected_fill==fmap[child['order_id']],(participation,extra,day,'fill reconstruction')
    dayfees+=cost;extra_fees+=cents(gross*D(extra)/10000);capacity=max(capacity,D(q)/D(bars[c][day]['volume']))
    seen_day.append(expected_fill);filled_seen.add(child['order_id'])
   for child in children:
    assert omap[child['order_id']]==child,(participation,extra,day,'complete child reconstruction')
   expected_all_children.extend(children)
  for parent in by_order[day]:
   state=states[parent['order_id']]
   if state['status']=='PENDING':state['status']='PARTIAL_DAY_EXPIRED' if state['filled_quantity'] else 'UNFILLED_DAY_EXPIRED'
   assert {k:parent[k] for k in state}==state,(day,'parent residual/status')
  assert seen_day==by_fill[day]
  quantities={c:sum(n for n,_,_ in ls) for c,ls in lots.items() if ls};assert quantities==ownership[day]
  for eid,e in events.items():
   if e['recorded']==day:
    assert not any(c==e['instrument'] for c,_,_,_ in stockclaims.values())
    q=quantities.get(e['instrument'],0);registered[eid]=q
    expected_ledger.append({'day':day,'kind':'RECORD_DATE_OWNERSHIP','event_id':eid,'instrument':e['instrument'],'quantity':q})
  assert entries==expected_ledger,(extra,day,'corporate ledger')
  for c,series in bars.items():
   bar=series[day]
   if bar['tradestatus']=='1':marks[c]=D(bar['close'])
   elif any(e['instrument']==c and e['ex_date']==day for e in events.values()):marks[c]=D(bar['preclose'])
   elif c not in marks and bar['close'] and D(bar['close'])>0:marks[c]=D(bar['close'])
  market=sum((q*marks[c] for c,q in quantities.items()),D(0));pending=sum((q*marks[c] for c,q,_,_ in stockclaims.values()),D(0))
  receivable=sum((net for _,net in claims.values()),D(0));equity=cash+market+pending+receivable
  expected=(cash,market,receivable,pending,equity,equity/previous-1,(market+pending)/equity,dayfees,paid)
  assert expected==tuple(D(row[k]) for k in ('cash','market_value','cash_receivable','pending_stock_value','equity','net_return','exposure','fees','net_dividend_cash_available')),(extra,day,'daily assets')
  nav[day]=equity;total_fees+=dayfees;previous=equity
  if day>='2024-01-02':count+=1
  if day=='2026-06-16':
   failed=failure_states[f'{participation}/{extra}']
   assert failed['cash']==str(cash) and failed['owned_shares']==quantities and failed['entitlements']==registered
   position_state={c:[{'quantity':n,'bought_on':bought,'price':str(price)} for n,bought,price in ls] for c,ls in lots.items() if ls}
   assert failed['positions']==position_state and failed['cash_claims']==cash_history and failed['stock_claims']==stock_history
  following=sessions[index+1] if index+1<len(sessions) else None
  if following in targets:
   assert day in by_intent;intent=by_intent[day];target=targets[following];assert target['as_of']==day and intent['execution_session']==following
   owned=dict(quantities)
   for c,q,_,_ in stockclaims.values():owned[c]=owned.get(c,0)+q
   assert D(intent['equity_at_decision'])==equity and intent['owned_integer_shares']==owned
   planned=[]
   for c in sorted(set(owned)|set(target['weights'])):
    weight=D(str(target['weights'].get(c,0)));held=owned.get(c,0)
    if not weight:
     if held:planned.append(('SELL',c,held))
     continue
    assert bars[c][day]['tradestatus']=='1'
    desired=int(equity*weight/marks[c]/100)*100
    if desired>held:
     q=(desired-held)//100*100
     if q:planned.append(('BUY',c,q))
    elif held>desired:planned.append(('SELL',c,held-desired))
   planned.sort(key=lambda x:(x[0]!='SELL',x[1]))
   assert planned==[(d['action'],d['security_id'],d['quantity']) for d in intent['decisions']]
   record={'record_id':digest({'policy':'low_beta60','formation':day,'target':target}),'kind':'frozen_target','available_at':intent['as_of'],'payload':target}
   visible=[record]
   for c in sorted(set(owned)|set(target['weights'])):
    content={'instrument':c,'as_of':day,'known_mark':str(marks[c]),'source_bar':bars[c][day]}
    visible.append({'record_id':digest(content),'kind':'raw_market_state','available_at':intent['as_of'],'payload':content})
   positions={c:{'quantity':quantities[c],'average_price':str(sum(n*price for n,_,price in ls)/quantities[c]),'mark_price':str(marks[c]),'mark_source':'VISIBLE_PRICE'} for c,ls in lots.items() if ls}
   wealth={'cash':str(cash),'positions':positions,'market_value':str(market),'cash_receivable':str(receivable),'pending_stock_value':str(pending),'equity':str(equity)}
   assert digest({'as_of':intent['as_of'],'records':visible,'account':wealth})==intent['snapshot_sha256'],(day,'snapshot')
   assert all(d['evidence_ids']==[record['record_id']] and d['reason']=='frozen monthly low_beta60 target, physical-share execution' for d in intent['decisions'])
   snapshot_count+=1
 assert count==675 and snapshot_count==34 and filled_seen==set(fmap) and len(registered)==269
 assert orders==expected_all_children
 assert len(expected_scenario)==1 and expected_scenario==v['scenario_ledger'],(participation,extra,'scenario ledger')
 assert expected_scenario[0]['registered_quantity']>0 and stated['scenario_uses']==1
 assert stated['account_sessions']==675 and stated['monthly_decisions']==34
 assert capacity<=1
 return {'status':'INDEPENDENT_CONDITIONAL_ACCOUNT_DAILY_FINANCIALS_RECONSTRUCTED','source_sessions':676,
  'account_sessions':count,'monthly_snapshots_reconstructed':snapshot_count,'events_reconstructed':len(registered),
  'parent_instructions_reconstructed':len(parents),'children_reconstructed':len(orders),'fills_reconstructed':len(fills),
  'corporate_ledger_entries':len(ledger),'scenario_uses_verified':len(expected_scenario),
  'scenario_registered_quantity':expected_scenario[0]['registered_quantity'],'scenario_capital_shares':expected_scenario[0]['capital_shares'],
  'scenario_cash_gross':expected_scenario[0]['cash_gross'],'scenario_stress_tax_reserve':expected_scenario[0]['stress_tax_reserve'],
  'pre_scenario_failure_typed_cash_shares_entitlements_claims_identical':True,'portfolio_returns_computed':False}

def main(argv=None):
 global base,repo,root,registry,sessions,bars,events,targets,tape_index,tape_cache,failure_states,development,development_summary
 parser=argparse.ArgumentParser()
 for n in ('source-root','repo-root','run-dir','plan','expected-plan-sha256','output'):parser.add_argument('--'+n,required=True)
 args=parser.parse_args(argv);base=Path(args.source_root);repo=Path(args.repo_root);root=Path(args.run_dir);out=Path(args.output);planfile=Path(args.plan)
 assert not out.exists() and sha(planfile)==args.expected_plan_sha256
 plan=read(planfile);assert plan['status']=='FROZEN_SIX_CONDITIONAL_ISSUER_SCHEDULE_ACCOUNTS_NO_ROI'
 assert plan['aggregate_ROI_in_replay_allowed'] is False and plan['source_queries_allowed'] is False and plan['investment_rule_changes_allowed'] is False
 assert plan['window']==['2023-12-29','2026-10-20'] and plan['initial_CNY']=='1000000'
 assert plan['participation_bps']==[100,500,1000] and plan['extra_cost_bps']==[20,40]
 assert root.resolve()==(base/plan['output_directory']).resolve()
 bindings(plan,(('extra_method_sha256',repo),('extra_public_sha256',repo),('extra_local_sha256',base)))
 originalplan=read(repo/'experiments/qlib/low-beta60-horizon-account-plan.json')
 bindings(originalplan,(('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)))
 eventplan=read(repo/'experiments/qlib/low-beta60-horizon-event-plan.json')
 assert sha(repo/'experiments/qlib/low-beta60-horizon-event-plan.json')=='3e6f7e1c1308d10ca6d98a7a9dc623d1fa67f188e793025f5b896ea3373dbb0d'
 bindings(eventplan,(('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)))
 summary=read(root/'summary.json');assert summary['plan_sha256']==sha(planfile)
 assert summary['all_profiles_complete'] is True and summary['scenario_classification']==CLASSIFICATION
 assert summary['window']==plan['window'] and summary['initial_CNY']=='1000000' and summary['source_queries']==0
 for k in ('statutory_exemption_verified','source_events_changed','portfolio_returns_computed','full_October_complete','sealed_evidence','historical_arrival_verified','queue_and_impact_calibrated','actual_FIFO_tax_liability_verified','candidate_promoted','objective_achieved'):assert summary[k] is False,k
 assert summary['results_by_profile']==read(root/'case_results.json') and set(summary['results_by_profile'])==PROFILES
 registry=read(repo/'experiments/qlib/low-beta60-issuer-schedule-scenario.json')
 bindings(registry,(('source_sha256',base),('public_evidence_sha256',repo)))
 assert registry['classification']==CLASSIFICATION and registry['investor_scope']=='ORDINARY_UNRESTRICTED_INDIVIDUAL'
 assert registry['statutory_exemption_verified'] is False and registry['strict_source_events_changed'] is False and registry['retrospective_evidence_evaluator_only'] is True
 assert registry['tax_model']=='FLAT20PERCENT_CASH_AND_VERIFIED_STOCK_INCOME_NO_ADDITIONAL_CAPITAL_RESERVE'
 assert digest(registry['event'])=='ddaec3e6088254e65a11c2e0c2fcad40bd35d4c405f1319b868b9362ccbf35b4'
 proposal=read(repo/'experiments/qlib/low-beta60-issuer-schedule-proposal-review.json')
 assert proposal['approved'] is True and proposal['proposal_sha256']==sha(repo/'experiments/qlib/low-beta60-issuer-schedule-scenario.json')
 assert proposal['protocol_doc_sha256']==sha(repo/'docs/research/low-beta60-issuer-schedule-scenario-2026-10-21.md')
 raw=base/'low-beta60-raw-horizon-20261021';manifest=read(raw/'manifest.json');sessions=read(raw/'calendar.json')['sessions']
 assert len(sessions)==676 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==['2023-12-29','2026-10-20']
 assert sha(raw/'calendar.json')==manifest['calendar_sha256'] and manifest['capture_complete'] is True
 bars={}
 for code,h in manifest['per_code_sha256'].items():
  f=raw/'codes'/(code+'.json');assert sha(f)==h;packet=read(f)
  assert packet['instrument']==code and [r['date'] for r in packet['bars']]==sessions and not packet['quarantine']
  bars[code]={r['date']:r for r in packet['bars']}
 assert len(bars)==79
 source=base/'low-beta60-account-source-events-horizon-20261021';ss=read(source/'summary.json');artifacts(source,ss['artifact_sha256'])
 sourceaudit=read(base/'low-beta60-horizon-event-independent-audit-20261021.json')
 assert sourceaudit['summary_sha256']==sha(source/'summary.json') and sourceaudit['verified_events']==269 and sourceaudit['full2026_reference_and_adjustment_coverage'] is True
 assert all(sourceaudit['semantic_negative_controls_rejected'].values()) and sourceaudit['unverified_tax_event_keys']==['SZ000937|2026-06-17']
 elist=read(source/'derived_events.json');events={e['event_id']:e for e in elist};assert len(events)==len(elist)==269
 assert events[registry['event']['event_id']]==registry['event'] and registry['event']['capital_tax_exempt_verified'] is False
 for proofname,pdfroot in (('effective_horizon_proofs.json','low-beta60-corporate-reviewed-horizon-20261021'),):
  for doc in read(source/proofname)['documents']:assert sha(base/pdfroot/doc['file'])==doc['sha256']
 originalsource=base/'low-beta60-account-source-events-20261021'
 for doc in read(originalsource/'effective_proofs.json')['documents']:assert sha(base/'low-beta60-corporate-reviewed-20261021'/doc['file'])==doc['sha256']
 development=base/'low-beta60-intraday-development-20261021';development_summary=read(development/'summary.json')
 assert read(base/'low-beta60-intraday-independent-audit-20261021.json')['summary_sha256']==sha(development/'summary.json')
 targets=read(base/'low-beta60-calendar-extension-formations-20261021/targets.json')['low_beta60']
 assert len(targets)==34 and {d:t for d,t in targets.items() if d<'2026-01-01'}==read(base/'low-beta60-pre2026-formations-20261021/targets.json')['low_beta60']
 assert {c for t in targets.values() for c in t['weights']}==set(bars)
 tape_index={};tape_cache={}
 for suffix,count,auditname,admissionname in (('dev',1332,'low-beta60-minute-independent-audit-20261021.json','low-beta60-minute-admission-20261021'),('2026',754,'low-beta60-2026-minute-independent-audit-20261021.json','low-beta60-minute-admission-2026-20261021')):
  cap=base/f'low-beta60-minutes-{suffix}-20261021';cm=read(cap/'manifest.json');assert len(cm['per_session_sha256'])==count and cm['complete_capture'] is True
  ma=read(base/auditname);admission=read(base/admissionname/'summary.json')
  assert ma['admission_summary_sha256']==sha(base/admissionname/'summary.json') and ma['source_pairs_reconstructed']==count and ma['reconstructed_source_admission_passes'] is True
  assert admission['capture_manifest_sha256']==sha(cap/'manifest.json') and admission['admitted_for_reconstructed_execution'] is True
  for name,h in cm['per_session_sha256'].items():
   code,day=name[:-5].split('-',1);f=cap/'sessions'/name;assert sha(f)==h and code in bars and day in bars[code]
   assert (code,day) not in tape_index;tape_index[(code,day)]=(f,h)
 assert len(tape_index)==2086
 failures=base/'low-beta60-intraday-horizon-20261021';failedsummary=read(failures/'summary.json')
 assert set(failedsummary['results_by_profile'])==PROFILES and failedsummary['all_profiles_complete'] is False and failedsummary['portfolio_returns_computed'] is False
 assert failedsummary['plan_sha256']==sha(repo/'experiments/qlib/low-beta60-horizon-account-plan.json')
 failure_states={}
 for profile,result in failedsummary['results_by_profile'].items():
  artifacts(failures/profile,result['failure_artifact_sha256'])
  assert result['error']=='applicable capital transfer tax treatment is unverified' and result['portfolio_returns_computed'] is False
  failure_states[profile]=read(failures/profile/'failed_account_state.json')
  assert failure_states[profile]['last_account_clock']==['2026-06-16',1]
 cases={};results={};prefixes=0
 for profile,stated in summary['results_by_profile'].items():
  participation,extra=map(int,profile.split('/'));v=load_case(root/profile,stated);cases[profile]=v
  prefixes+=prefix_checks(v,profile);results[profile]=audit(v,participation,extra,stated)
 assert prefixes==42
 negatives={};reference='100/40'
 for name in ('erased_fee','false_daily_equity','false_record_quantity','wrong_target_quantity','wrong_previous_window_volume','unfilled_child_forged_as_filled','scenario_quantity','scenario_tax_reserve','scenario_strict_flag','scenario_classification'):
  v=copy.deepcopy(cases[reference])
  if name=='erased_fee':v['fills'][0]['cost']='0'
  elif name=='false_daily_equity':v['rows'][-1]['equity']=str(D(v['rows'][-1]['equity'])+1)
  elif name=='false_record_quantity':next(x for x in v['corporate_ledger'] if x['kind']=='RECORD_DATE_OWNERSHIP')['quantity']+=100
  elif name=='wrong_target_quantity':v['intents'][0]['decisions'][0]['quantity']+=100
  elif name=='wrong_previous_window_volume':v['orders'][0]['source_volume_lower_shares']+=100
  elif name=='unfilled_child_forged_as_filled':next(o for o in v['orders'] if o['status'].startswith('UNFILLED'))['status']='FILLED'
  elif name=='scenario_quantity':v['scenario_ledger'][0]['capital_shares']+=1
  elif name=='scenario_tax_reserve':v['scenario_ledger'][0]['stress_tax_reserve']='0'
  elif name=='scenario_strict_flag':v['scenario_ledger'][0]['original_strict_flag']=True
  else:v['scenario_ledger'][0]['classification']='STATUTORY_EXEMPTION'
  try:audit(v,100,40,summary['results_by_profile'][reference])
  except (AssertionError,KeyError):negatives[name]=True
  else:raise AssertionError('semantic negative accepted:'+name)
 # Recheck every bound input after reconstruction, preserving unchanged-source evidence.
 bindings(plan,(('extra_method_sha256',repo),('extra_public_sha256',repo),('extra_local_sha256',base)))
 bindings(originalplan,(('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)))
 result={'status':'INDEPENDENT_SIX_CONDITIONAL_ACCOUNTS_DAILY_FINANCIALS_AND_PREFIXES_VERIFIED',
  'audit_code_sha256':sha(__file__),'plan_sha256':sha(planfile),'summary_sha256':sha(root/'summary.json'),
  'all_six_accounts_reconstructed':True,'original_269_events_unchanged':True,'original_42_financial_prefixes_identical':True,
  'exact_single_conditional_event_only':True,'original_failure_four_ledger_prefixes_identical_per_profile':True,
  'portfolio_returns_computed':False,'critical_or_important_findings':0,'profiles':results,
  'arithmetic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,
  'all2086_minute_source_bodies_hash_authenticated':True,'reconstructed_accessed_minute_pairs':len(tape_cache),
  'imports_project_code':False,'new_source_queries':0,'statutory_exemption_verified':False,
  'historical_arrival_verified':False,'queue_and_impact_calibrated':False,'actual_FIFO_tax_liability_verified':False,
  'full_October_complete':False,'objective_achieved':False,
  'trust_and_limitations':['Authenticates and relies on previously reviewed event-source and minute-admission audits; does not independently prove issuer interpretation or statutory exemption.',
   'Reconstructs every persisted daily asset, claim, physical lot, execution window, order/fill and monthly snapshot with stdlib arithmetic; does not execute project account or compute aggregate period ROI.',
   'Conditional scenario applies only to unchanged SZ000937 June17 event, ordinary unrestricted individual, under fixed20percent cash+verified-stock-income reserve; qualifying issuance-premium origin remains unresolved.',
   'Prior frozen sources and six strict-account failures remain preserved; queue/impact calibration, historical arrival, actualFIFO tax settlement and full October remain unverified.']}
 with out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print('All6 conditional accounts independently reconstructed;42 old financial prefixes and24 strict-failure ledger prefixes verified; no aggregate ROI')
 return 0
if __name__=='__main__':raise SystemExit(main())
