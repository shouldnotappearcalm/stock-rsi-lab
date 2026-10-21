"""Independent stdlib fixed-composite intraday account audit; no runtime imports or queries."""
import argparse,copy,csv,hashlib,json,math
from collections import defaultdict
from datetime import datetime,timedelta
from decimal import Decimal as D,ROUND_HALF_UP,ROUND_DOWN,ROUND_UP
from pathlib import Path
from zoneinfo import ZoneInfo
p=argparse.ArgumentParser()
for n in ('source-root','run-dir','repo-root','output'):p.add_argument('--'+n,required=True)
p.add_argument('--source-only',action='store_true')
a=p.parse_args();base=Path(a.source_root);root=Path(a.run_dir);repo=Path(a.repo_root)
if not __debug__:raise RuntimeError('audit assertions must remain enabled')
assert not Path(a.output).exists(), 'preserve previous audit result'
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
read=lambda f:json.loads(Path(f).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def cents(v):return v.quantize(D('.01'),rounding=ROUND_HALF_UP)
def at(day,clock):return datetime.fromisoformat(day+'T'+clock+'+08:00').astimezone(ZoneInfo('UTC')).isoformat()
def localday(ts):return datetime.fromisoformat(ts).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
planfile=repo/'experiments/qlib/szse-value-momentum-intraday-plan.json'
assert sha(planfile)=='5aceef3f4493c30e6b35a64dbd3caa13d0c52ad7f0f70a2faf9d36aaa301c29c'
plan=read(planfile)
assert plan['status']=='FROZEN_COMPOSITE_PRE2026_INTRADAY_DEVELOPMENT' and plan['candidate']=='szse_value_momentum_equal'
assert plan['candidate_budget']==1 and plan['initial_CNY']=='1000000' and plan['extra_cost_bps']==[20,40] and plan['participation_bps']==[100,500,1000]
for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
 for f,h in plan[field].items():
  assert not Path(f).is_absolute() and '..' not in Path(f).parts and sha(parent/f)==h,(f,'binding')
rawplan=read(repo/'experiments/qlib/szse-value-momentum-raw-daily-plan.json')
assert sha(repo/'experiments/qlib/szse-value-momentum-raw-daily-plan.json')==plan['raw_daily_plan_sha256']
for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
 for f,h in rawplan[field].items():assert sha(parent/f)==h
source=base/'szse-value-momentum-account-sources-20261021';ss=read(source/'summary.json')
sourceaudit=read(base/'szse-value-momentum-source-projection-independent-audit-20261021.json')
assert sourceaudit['summary_sha256']==sha(source/'summary.json') and sourceaudit['events_reconstructed']==255
assert sourceaudit['plan_sha256']==plan['raw_daily_plan_sha256'] and sourceaudit['imports_project_code'] is False
assert sourceaudit['negative_controls_rejected'] and all(sourceaudit['negative_controls_rejected'].values())
for f,h in ss['artifact_sha256'].items():assert sha(source/f)==h
raw=base/'szse-value-momentum-raw-dev-20261021';m=read(raw/'manifest.json')
assert sha(raw/'manifest.json')==ss['raw_manifest_sha256']
sessions=read(raw/'calendar.json')['sessions'];assert len(sessions)==486 and sessions==sorted(set(sessions))
assert sessions[0]=='2023-12-29' and sessions[-1]=='2025-12-31' and sha(raw/'calendar.json')==m['calendar_sha256']
bars={};packets={}
for c,h in m['per_code_sha256'].items():
 f=raw/'codes'/(c+'.json');assert sha(f)==h;v=read(f);packets[c]=v
 assert v['instrument']==c and v['window']==['2023-12-29','2025-12-31'] and digest(v)==ss['original_packet_digests'][c]
 expected=[x for x in sessions if x>='2024-04-02'] if c=='SZ001389' else sessions
 assert [r['date'] for r in v['bars']]==expected
 bars[c]={r['date']:r for r in v['bars']}
tf=base/'szse-value-momentum-formations-pre2026-20261021/targets.json'
assert sha(tf)==ss['target_sha256']==m['target_sha256']==plan['candidate_targets_sha256']
targets=read(tf)['szse_value_momentum_equal'];assert len(targets)==24 and len(bars)==103
assert set().union(*(set(t['weights']) for t in targets.values()))==set(bars)
elist=read(source/'derived_events.json');events={e['event_id']:e for e in elist};assert len(events)==len(elist)==255
receipts=read(source/'event_source_receipts.json');proof=read(source/'reviewed-manifest.json')
assert len(receipts)==255 and {r['event_id'] for r in receipts}==set(events)
assert sum(r['source_kind']=='VENDOR_DISTRIBUTION' for r in receipts)==254
assert sum(r['source_kind']=='PRIMARY_NOTICE_SUPPLEMENT' for r in receipts)==1
for doc in proof['documents']:assert sha(base/'szse-value-momentum-primary-capture-20261021'/doc['file'])==doc['sha256']
for r in receipts:
 e=events[r['event_id']]
 rows=packets[e['instrument']]['distributions'] if r['source_kind']=='VENDOR_DISTRIBUTION' else [s['record'] for s in proof['supplementary_distributions'] if s['instrument']==e['instrument']]
 matches=[row for row in rows if digest(row)==r['source_row_sha256']];assert len(matches)==1
 row=matches[0];assert e['recorded']==row['dividRegistDate'] and e['ex_date']==row['dividOperateDate'] and e['pay_date']==row['dividPayDate']
 assert D(e['cash_per_share'])==D(row['dividCashPsBeforeTax'] or '0') and D(e['stock_per_share'])==D(row['dividStocksPs'] or '0') and D(e['capital_per_share'])==D(row['dividReserveToStockPs'] or '0')
assert len(proof['capital_tax'])==4 and proof['strict_statutory_capital_tax_certification'] is False
life=read(source/'lifecycles.json');anchor=read(source/'listing_anchor_receipt.json')
assert life==sourceaudit['listing_lifecycle'] and anchor==sourceaudit['listing_anchor_receipt']
missing_sessions=[s for s in sessions if s<'2024-04-02'];assert len(missing_sessions)==60 and anchor['prelisting_missing_sessions']==missing_sessions
assert anchor['synthetic_prices_created']==0 and anchor['entitlement_inferred'] is False
capture=base/'szse-value-momentum-minutes-dev-20261021';cm=read(capture/'manifest.json')
ad=base/'szse-value-momentum-minute-admission-20261021';admission=read(ad/'summary.json')
minuteaudit=read(repo/'experiments/qlib/szse-value-momentum-minute-admission-independent-audit.json')
assert minuteaudit['admission_summary_sha256']==sha(ad/'summary.json') and minuteaudit['reconstructed_source_admission_passes'] is True
assert minuteaudit['source_pairs_reconstructed']==1744 and minuteaudit['imports_project_code'] is False
assert minuteaudit['semantic_negative_controls_rejected'] and all(minuteaudit['semantic_negative_controls_rejected'].values())
assert minuteaudit['audit_code_sha256']==plan['admission_audit_code_sha256']==sha(repo/'experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-minute-admission-audit.py')
assert admission['capture_manifest_sha256']==sha(capture/'manifest.json') and admission['admitted_for_reconstructed_execution'] is True
assert admission['status_counts']=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':1744} and sha(ad/'details.json')==admission['details_sha256']
assert len(cm['per_session_sha256'])==1744 and cm['complete_capture'] is True
assert sha(capture/'plan.json')==cm['plan_sha256']
tape_cache={}
def tape(code,day):
 assert day<='2025-12-31';key=(code,day);name=code+'-'+day+'.json';f=capture/'sessions'/name
 if key in tape_cache:return tape_cache[key]
 assert sha(f)==cm['per_session_sha256'][name]
 packet=read(f);assert packet['instrument']==code and packet['requested_day']==day
 points=packet.get('methods',{}).get('minutes.history',packet)['response']['points'];assert len(points)==240
 clocks=[f'{h:02d}:{m:02d}:00' for h in range(9,16) for m in range(60) if '09:31'<=f'{h:02d}:{m:02d}'<='11:30' or '13:01'<=f'{h:02d}:{m:02d}'<='15:00']
 assert len(clocks)==240
 for point,clock in zip(points,clocks):
  assert datetime.fromisoformat(point['time'])==datetime.fromisoformat(at(day,clock))
  assert type(point['volume']) is int and point['volume']>=0 and type(point['price_milli']) is int and point['price_milli']>0
  if point['volume']>0:assert point['price_milli']%10==0
 windows=[]
 for n in range(0,240,5):
  block=points[n:n+5];end=datetime.fromisoformat(block[-1]['time']).astimezone(ZoneInfo('UTC'));start=end-timedelta(minutes=5)
  prices=[D(x['price_milli'])/1000 for x in block if x['volume']>0]
  windows.append({'start':start.isoformat(),'end':end.isoformat(),'volume':sum(max(0,x['volume']*100-100) for x in block),
   'buy':max(prices) if prices else None,'sell':min(prices) if prices else None,
   'evidence':digest({'security_id':code,'day':day,'points':[{'time':x['time'],'volume':x['volume'],'price_milli':x['price_milli']} for x in block]})})
 assert sum(w['volume'] for w in windows)<=D(bars[code][day]['volume'])
 tape_cache[key]=windows;return windows

for name in cm['per_session_sha256']:
 assert Path(name).name==name
 code,day=name[:-5].split('-',1);assert day in sessions and code in bars and day in bars[code]
 assert bars[code][day]['tradestatus']=='1'
 tape(code,day)
assert len(tape_cache)==1744
if a.source_only:
 result={'status':'STDLIB_COMPOSITE_INTRADAY_SOURCE_PREFLIGHT_PASSED','audit_code_sha256':sha(__file__),
  'plan_sha256':sha(planfile),'original_raw_packets':103,'source_sessions':486,'events_bound_to_original_rows':255,
  'primary_listing_absent_sessions':60,'minute_pairs_reconstructed':len(tape_cache),
  'portfolio_returns_computed':False,'network_queries':0,'imports_project_code':False,'new_2026_values_read':False}
 Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));raise SystemExit(0)
summary=read(root/'summary.json')
assert summary['plan_sha256']==sha(planfile) and summary['method_code_sha256']==plan['method_code_sha256']
assert set(summary['results_by_profile'])=={f'{p}/{e}' for p in (100,500,1000) for e in (20,40)}
assert summary['phase']=='dev' and summary['candidate']=='szse_value_momentum_equal' and summary['window']==['2023-12-29','2025-12-31']
for flag in ('historical_arrival_verified','full_corporate_actions_certified','queue_and_impact_calibrated','actual_FIFO_tax_liability_verified','strict_statutory_tax_certification','2026_strategy_returns_queried','candidate_promoted','objective_achieved'):assert summary[flag] is False
assert summary['tax_model']=='FIXED20PCT_CASH_STRESS_NOT_FIFO' and summary['inherited_capital_tax_inferences']==4
assert sha(root/'derived_events.json')==summary['derived_events_sha256'] and read(root/'derived_events.json')==elist
assert sha(root/'event_source_receipts.json')==summary['event_source_receipts_sha256'] and read(root/'event_source_receipts.json')==receipts

def close(x,y):assert math.isclose(x,y,rel_tol=1e-9,abs_tol=1e-6),(x,y)
def field_at(code,field,day,asof):
 assert day==asof and day<='2025-12-31' and field in ('close','factor')
 return float(bars[code][day]['close']) if field=='close' else 1.

def equivalent(actual, expected):
    if isinstance(expected, dict):
        assert set(actual)==set(expected), (set(actual),set(expected))
        for key in expected:equivalent(actual[key],expected[key])
    elif isinstance(expected, (list,tuple)):
        assert len(actual)==len(expected)
        for a,b in zip(actual,expected):equivalent(a,b)
    elif isinstance(expected,bool) or expected is None or isinstance(expected,str):
        assert actual==expected and type(actual)==type(expected)
    else:close(float(actual),float(expected))
def independent_allocation(equity, held, weights, asof):
    budget=equity*math.fsum(weights.values());q={};quotes={};desired={};options=[]
    for c in sorted(c for c,w in weights.items() if w>0):
        p=field_at(c,'close',asof,asof);f=field_at(c,'factor',asof,asof)
        assert p is not None and p>0 and f is not None and f>0
        lot=100/f;lot_value=100*p/f;v=equity*weights[c];current=held.get(c,0.)
        desired[c]=v;quotes[c]=(p,f,lot)
        if current*p<=v:
            count=math.floor((v-current*p)/lot_value+1e-10)
            q[c]=current+count*lot
        else:q[c]=math.floor(v/lot_value+1e-10)*lot
        trial=q[c]+lot;action='ONE_BUY_LOT'
        if current*p>v:
            trial=min(trial,current)
            action='CANCEL_REMAINING_SELL' if trial==current else 'REDUCE_SELL_ONE_LOT'
        expense=(trial-q[c])*p
        gap=v-q[c]*p
        improvement=gap**2-(v-trial*p)**2
        if expense>0 and improvement>0:
            options.append((float(format(improvement,'.12g')),c,trial,expense,improvement,action))
    initial=math.fsum(q[c]*quotes[c][0] for c in q)
    before=math.fsum((desired[c]-q[c]*quotes[c][0])**2 for c in q)
    remaining=budget-initial;steps=[]
    for _,c,trial,expense,improvement,action in sorted(options,key=lambda r:(-r[0],r[1])):
        if expense<=remaining+max(1e-8,equity*1e-10):
            steps.append({'instrument':c,'normalized_units_added':trial-q[c],
                'notional_added':expense,'squared_error_reduction':improvement,'action':action})
            q[c]=trial;remaining-=expense
    orders=[]
    for c,current in held.items():
        if current>0 and weights.get(c,0.)==0:
            orders.append({'instrument':c,'side':'SELL','normalized_units':current,
                'known_normalized_close':None,'known_factor':None,'as_of':asof,
                'quantity_basis':'KNOWN_INVENTORY_FULL_EXIT'})
    for c in sorted(q):
        current=held.get(c,0.);change=q[c]-current;p,f,lot=quotes[c]
        if abs(change)<=1e-8*max(1.,current,q[c]):continue
        if change>0:assert math.isclose(change*f/100,round(change*f/100),rel_tol=1e-10,abs_tol=1e-8)
        orders.append({'instrument':c,'side':'BUY' if change>0 else 'SELL',
            'normalized_units':abs(change),'known_normalized_close':p,'known_factor':f,
            'as_of':asof,'quantity_basis':'PRIOR_CLOSE_BUDGETED_LOT_TARGET'})
    final=math.fsum(q[c]*quotes[c][0] for c in q)
    after=math.fsum((desired[c]-q[c]*quotes[c][0])**2 for c in q)
    assert final<=budget+max(1e-8,equity*1e-10) and after<=before+max(1e-8,before*1e-10)
    receipt={'as_of':asof,'target_notional_budget':budget,'initial_planned_notional':initial,
        'final_planned_notional':final,'unallocated_notional_budget':budget-final,
        'squared_tracking_error_before':before,'squared_tracking_error_after':after,
        'post_order_normalized_positions':q,'allocation_steps':steps,
        'execution_prices_or_returns_used':False,'future_cash_or_fill_guaranteed':False}
    return sorted(orders,key=lambda o:(o['side']!='SELL',o['instrument'])),receipt

def legal_quantity(remaining,capacity,side):
 cap=min(remaining,capacity,1000000)
 return remaining if side=='SELL' and remaining<=cap else cap//100*100

def fee(gross,side,extra):return cents(max(D(5),gross*D('.0005' if side=='BUY' else '.0015')))+cents(gross*D(extra)/10000)
def load_case(folder,stated):
 assert stated['status']=='NESTED_EXECUTION_ACCOUNT_RECONCILED'
 for f,h in stated['artifact_sha256'].items():assert sha(folder/f)==h
 v={n:read(folder/(n+'.json')) for n in ('orders','fills','corporate_ledger','ownership','intents','parent_instructions')}
 with (folder/'daily.csv').open() as stream:v['rows']=list(csv.DictReader(stream))
 return v

def audit(v,participation,extra,stated):
 rows=v['rows'];orders=v['orders'];fills=v['fills'];ledger=v['corporate_ledger'];ownership=v['ownership'];intents=v['intents'];parents=v['parent_instructions']
 assert [r['day'] for r in rows]==sessions and set(ownership)==set(sessions)
 assert len(intents)==24 and len({i['execution_session'] for i in intents})==24
 by_intent={localday(i['as_of']):i for i in intents};assert len(by_intent)==24
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
 cash=D('1000000');previous=cash;peak=cash;dd=D(0);lots=defaultdict(list);marks={};claims={};stockclaims={};registered={};nav={}
 total_fees=D(0);extra_fees=D(0);gross_div=D(0);tax=D(0);capacity=D(0);exposure_sum=D(0);count=0;filled_seen=set();snapshot_count=0
 for index,row in enumerate(rows):
  day=row['day'];entries=by_ledger[day];expected_ledger=[];dayfees=D(0);paid=D(0)
  for eid,(available,net) in list(claims.items()):
   if available==day:
    expected_ledger.append({'day':day,'kind':'NET_DIVIDEND_CASH_AVAILABLE','event_id':eid,'cash_delta':str(net)})
    cash+=net;paid+=net;del claims[eid]
  for eid,e in events.items():
   if e['ex_date']!=day:continue
   q=registered[eid];gross=cents(D(e['cash_per_share'])*q);income=cents(D(e['stock_taxable_income_per_share'])*q)
   reserve=cents((gross+income)*D('.2'));cap=D(e['capital_per_share'])*q;stock=D(e['stock_per_share'])*q
   assert cap==int(cap) and stock==int(stock) and reserve<=gross
   assert not q or not cap or e['capital_tax_exempt_verified'] is True
   assert not q or not stock or e['stock_tax_basis_verified'] is True
   if gross:claims[eid]=(next((s for s in sessions if s>e['pay_date']),None),gross-reserve)
   for amount,kind in ((int(cap),'CAPITAL_SHARES_LISTED'),(int(stock),'STOCK_DIVIDEND_SHARES_LISTED')):
    if amount:stockclaims[(eid,kind)]=(e['instrument'],amount,e['listed'],e['recorded'])
   expected_ledger.append({'day':day,'kind':'EX_DATE_ENTITLEMENT','event_id':eid,'instrument':e['instrument'],
    'registered_quantity':q,'cash_gross':str(gross),'stress_tax_reserve':str(reserve),
    'capital_shares':int(cap),'stock_shares':int(stock),'taxable_stock_income':str(income)})
   gross_div+=gross;tax+=reserve
  for key,(code,q,listed,recorded) in list(stockclaims.items()):
   if listed<=day:
    lots[code].append([q,recorded,D(0)]);del stockclaims[key]
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
   if day not in series:
    assert c=='SZ001389' and day<'2024-04-02' and c not in quantities and not any(c==z[0] for z in stockclaims.values())
    assert c not in {o['security_id'] for o in by_order[day]}
    marks.pop(c,None);continue
   bar=series[day]
   if bar['tradestatus']=='1':marks[c]=D(bar['close'])
   elif any(e['instrument']==c and e['ex_date']==day for e in events.values()):marks[c]=D(bar['preclose'])
   elif c not in marks and bar['close'] and D(bar['close'])>0:marks[c]=D(bar['close'])
  market=sum((q*marks[c] for c,q in quantities.items()),D(0));pending=sum((q*marks[c] for c,q,_,_ in stockclaims.values()),D(0))
  receivable=sum((net for _,net in claims.values()),D(0));equity=cash+market+pending+receivable
  expected=(cash,market,receivable,pending,equity,equity/previous-1,(market+pending)/equity,dayfees,paid)
  assert expected==tuple(D(row[k]) for k in ('cash','market_value','cash_receivable','pending_stock_value','equity','net_return','exposure','fees','net_dividend_cash_available')),(extra,day,'daily assets')
  nav[day]=equity;total_fees+=dayfees;previous=equity
  if day>='2024-01-02':exposure_sum+=(market+pending)/equity;count+=1;peak=max(peak,equity);dd=min(dd,equity/peak-1)
  following=sessions[index+1] if index+1<len(sessions) else None
  if following in targets:
   assert day in by_intent;intent=by_intent[day];target=targets[following];assert target['as_of']==day and intent['execution_session']==following
   owned=dict(quantities)
   for c,q,_,_ in stockclaims.values():owned[c]=owned.get(c,0)+q
   assert D(intent['equity_at_decision'])==equity and intent['owned_integer_shares']==owned
   independent_orders,allocation=independent_allocation(float(equity),owned,{c:float(D(str(w))) for c,w in target['weights'].items()},day)
   planned=[(o['side'],o['instrument'],int(o['normalized_units'])) for o in independent_orders]
   assert all(o['normalized_units']==int(o['normalized_units']) for o in independent_orders)
   assert planned==[(d['action'],d['security_id'],d['quantity']) for d in intent['decisions']]
   equivalent(intent['allocation_receipt'],{**allocation,'coordinate_basis':'ONE_UNIT_EQUALS_ONE_RAW_SHARE',
    'observed_adjustment_factor_used':False,'physical_integer_orders':True})
   record={'record_id':digest({'policy':'szse_value_momentum_equal','formation':day,'target':target}),'kind':'frozen_target','available_at':intent['as_of'],'payload':target}
   visible=[record]
   for c in sorted(set(owned)|set(target['weights'])):
    content={'instrument':c,'as_of':day,'known_mark':str(marks[c]),'source_bar':bars[c][day]}
    visible.append({'record_id':digest(content),'kind':'raw_market_state','available_at':intent['as_of'],'payload':content})
   positions={c:{'quantity':quantities[c],'average_price':str(sum(n*price for n,_,price in ls)/quantities[c]),'mark_price':str(marks[c]),'mark_source':'VISIBLE_PRICE'} for c,ls in lots.items() if ls}
   wealth={'cash':str(cash),'positions':positions,'market_value':str(market),'cash_receivable':str(receivable),'pending_stock_value':str(pending),'equity':str(equity)}
   assert digest({'as_of':intent['as_of'],'records':visible,'account':wealth})==intent['snapshot_sha256'],(day,'snapshot')
   assert all(d['evidence_ids']==[record['record_id']] and d['reason']=='frozen monthly szse_value_momentum_equal target, physical-share execution' for d in intent['decisions'])
   snapshot_count+=1
 assert count==485 and snapshot_count==24 and filled_seen==set(fmap) and len(registered)==255
 assert orders==expected_all_children
 r24=(nav['2024-12-31']/D('1000000')-1)*100;r25=(nav['2025-12-31']/nav['2024-12-31']-1)*100;exposure=exposure_sum/count*100
 for key,vv in (('2024_return_pct',r24),('2025_return_pct',r25),('average_exposure_pct',exposure),('max_drawdown_pct',dd*100),('max_order_fraction_of_whole_day_volume',capacity)):
  assert abs(float(vv)-stated[key])<1e-10
 assert stated['primary_bound_absent_sessions']==60 and stated['account_sessions']==485 and stated['monthly_decisions']==24
 assert stated['noncash_entitlements_supported'] is True and stated['all_children_within_1million_shares'] is True
 assert len(fills)==stated['fills'] and len(orders)==stated['child_orders']==stated['orders'] and len(parents)==stated['parent_instructions'] and capacity<=1 and stated['whole_day_volume_violations']==0
 return {'status':'INDEPENDENT_PHYSICAL_INTRADAY_ACCOUNT_RECONSTRUCTED','source_sessions':486,'account_sessions':count,'primary_bound_absent_sessions_verified':60,
  'monthly_intents_and_snapshots_reconstructed':snapshot_count,'record_and_ex_events_reconstructed':255,'corporate_ledger_entries':len(ledger),
  'parent_instructions_reconstructed':len(parents),'children_and_statuses_reconstructed':len(orders),'fills_reconstructed':len(fills),'2024_return_pct':float(r24),'2025_return_pct':float(r25),
  'average_exposure_pct':float(exposure),'max_drawdown_pct':float(dd*100),'ending_equity_CNY':str(nav[sessions[-1]]),
  'total_fees_CNY':str(total_fees),'extra_fees_CNY':str(extra_fees),'gross_dividends_CNY':str(gross_div),'flat_stress_tax_CNY':str(tax)}

results={};cases={}
for profile,stated in summary['results_by_profile'].items():
 participation,extra=map(int,profile.split('/'));cases[profile]=load_case(root/profile,stated)
 results[profile]=audit(cases[profile],participation,extra,stated)
negatives={};reference='100/40'
for name in ('erased_fee','false_daily_equity','false_record_quantity','wrong_target_quantity','wrong_previous_window_volume','unfilled_child_forged_as_filled','allocation_receipt_budget','future_child_clock','parent_residual','prior_window_clock'):
 v=copy.deepcopy(cases[reference])
 if name=='erased_fee':v['fills'][0]['cost']='0'
 elif name=='false_daily_equity':v['rows'][-1]['equity']=str(D(v['rows'][-1]['equity'])+1)
 elif name=='false_record_quantity':next(x for x in v['corporate_ledger'] if x['kind']=='RECORD_DATE_OWNERSHIP')['quantity']+=100
 elif name=='wrong_target_quantity':v['intents'][0]['decisions'][0]['quantity']+=100
 elif name=='wrong_previous_window_volume':v['orders'][0]['source_volume_lower_shares']+=100
 elif name=='unfilled_child_forged_as_filled':
  o=v['orders'][0];o['status']='FILLED' if o['status']!='FILLED' else 'UNFILLED_VOLUME_OR_PRICE'
 elif name=='allocation_receipt_budget':v['intents'][0]['allocation_receipt']['target_notional_budget']+=100
 elif name=='future_child_clock':v['orders'][0]['submitted_at']=v['orders'][0]['expires_at']
 elif name=='parent_residual':v['parent_instructions'][0]['remaining']+=100
 else:v['orders'][0]['source_volume_as_of']=v['orders'][0]['expires_at']
 try:audit(v,100,40,summary['results_by_profile'][reference])
 except (AssertionError,KeyError):negatives[name]=True
 else:raise AssertionError('arithmetic negative control accepted:'+name)
passes=all(min(results[f'{p}/40']['2024_return_pct'],results[f'{p}/40']['2025_return_pct'])>0 and results[f'{p}/40']['average_exposure_pct']>=90 for p in (100,500,1000))
assert passes==summary['raw_development_confirmation_passes']
result={'status':'INDEPENDENT_COMPOSITE_INTRADAY_DEVELOPMENT_AUDIT_COMPLETE','audit_code_sha256':sha(__file__),
 'plan_sha256':sha(planfile),'summary_sha256':sha(root/'summary.json'),'imports_project_code':False,
 'results_by_profile':results,'arithmetic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,
 'development_confirmation_passes_independently':passes,'reconstructed_minute_pairs':len(tape_cache),
 'all_profile_parent_child_fill_quantities_and_snapshots_reconstructed':True,
 'total_monthly_snapshots_reconstructed':sum(r['monthly_intents_and_snapshots_reconstructed'] for r in results.values()),
 'tax_model':'FIXED20PCT_CASH_STRESS_NOT_FIFO','inherited_capital_tax_inferences':4,
 'exact_source_share_precision_certified':False,'strict_statutory_tax_certification':False,
 'historical_arrival_verified':False,'full_corporate_actions_certified':False,'actual_FIFO_tax_liability_verified':False,
 'queue_and_impact_calibrated':False,'2026_return_computed':False,'new_2026_queries':False,'candidate_promoted':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('All6intraday accounts reconstructed:144budgeted snapshots,255events each, allparents/children/fees;10semantic negatives rejected')
