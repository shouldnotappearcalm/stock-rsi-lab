"""Stdlib audit: physical lots, source events, every order and visible snapshot."""
import argparse,copy,csv,hashlib,json,math
from collections import defaultdict
from datetime import datetime
from decimal import Decimal as D,ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo
p=argparse.ArgumentParser()
for n in ('source-root','run-dir','repo-root','expected-plan-sha256','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);root=Path(a.run_dir);repo=Path(a.repo_root)
if not __debug__:raise RuntimeError('audit assertions must remain enabled')
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
read=lambda f:json.loads(Path(f).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def cents(v):return v.quantize(D('.01'),rounding=ROUND_HALF_UP)
def at(day,clock):return datetime.fromisoformat(day+'T'+clock+'+08:00').astimezone(ZoneInfo('UTC')).isoformat()
def localday(ts):return datetime.fromisoformat(ts).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
planfile=repo/'experiments/qlib/szse-value-momentum-raw-daily-plan.json'
assert sha(planfile)==a.expected_plan_sha256
plan=read(planfile);summary=read(root/'summary.json')
assert plan['candidate']=='szse_value_momentum_equal' and plan['initial_CNY']=='1000000' and plan['extra_cost_bps']==[20,40]
assert summary['plan_sha256']==sha(planfile) and summary['method_code_sha256']==plan['method_code_sha256']
for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
 for f,h in plan[field].items():assert sha(parent/f)==h
source=base/'szse-value-momentum-account-sources-20261021';ss=read(source/'summary.json')
sourceaudit=read(base/'szse-value-momentum-source-projection-independent-audit-20261021.json')
assert sourceaudit['summary_sha256']==sha(source/'summary.json') and sourceaudit['events_reconstructed']==255
assert all(sourceaudit['negative_controls_rejected'].values()) and sourceaudit['imports_project_code'] is False
for f,h in ss['artifact_sha256'].items():assert sha(source/f)==h
assert summary['source_projection_summary_sha256']==sha(source/'summary.json')
raw=base/'szse-value-momentum-raw-dev-20261021';m=read(raw/'manifest.json')
assert sha(raw/'manifest.json')==ss['raw_manifest_sha256']
sessions=read(raw/'calendar.json')['sessions'];assert len(sessions)==486 and sessions==sorted(set(sessions))
assert sessions[0]=='2023-12-29' and sessions[-1]=='2025-12-31' and sha(raw/'calendar.json')==m['calendar_sha256']
bars={}
for c,h in m['per_code_sha256'].items():
 f=raw/'codes'/(c+'.json');assert sha(f)==h;v=read(f)
 assert v['instrument']==c and v['window']==['2023-12-29','2025-12-31']
 expected=[d for d in sessions if d>='2024-04-02'] if c=='SZ001389' else sessions
 assert [r['date'] for r in v['bars']]==expected
 bars[c]={r['date']:r for r in v['bars']}
tf=base/'szse-value-momentum-formations-pre2026-20261021/targets.json';assert sha(tf)==ss['target_sha256']==m['target_sha256']
targets=read(tf)['szse_value_momentum_equal'];assert len(targets)==24 and len(bars)==103
elist=read(source/'derived_events.json');events={e['event_id']:e for e in elist};assert len(events)==len(elist)==255
assert set(summary['results_by_extra_bps'])=={'20','40'}
for flag in ('minute_execution_admitted','historical_arrival_certified','strict_statutory_tax_certification','queue_and_impact_calibrated','new_2026_market_queries','candidate_promoted','objective_achieved'):assert summary[flag] is False
assert summary['tax_model']=='FIXED20PCT_CASH_STRESS_NOT_FIFO' and summary['inherited_capital_tax_inferences']==4

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

def fee(gross,side,extra):return cents(max(D(5),gross*D('.0005' if side=='BUY' else '.0015')))+cents(gross*D(extra)/10000)
def load_case(folder,stated):
 assert stated['status']=='DAILY_PROXY_ACCOUNT_RECONCILED'
 for f,h in stated['artifact_sha256'].items():assert sha(folder/f)==h
 v={n:read(folder/(n+'.json')) for n in ('orders','fills','corporate_ledger','ownership','intents')}
 with (folder/'daily.csv').open() as stream:v['rows']=list(csv.DictReader(stream))
 return v

def audit(v,extra,stated):
 rows=v['rows'];orders=v['orders'];fills=v['fills'];ledger=v['corporate_ledger'];ownership=v['ownership'];intents=v['intents']
 assert [r['day'] for r in rows]==sessions and set(ownership)==set(sessions)
 assert len(intents)==24 and len({i['execution_session'] for i in intents})==24
 by_intent={localday(i['as_of']):i for i in intents};assert len(by_intent)==24
 by_order=defaultdict(list);by_ledger=defaultdict(list);by_fill=defaultdict(list)
 for o in orders:by_order[localday(o['eligible_at'])].append(o)
 for x in ledger:by_ledger[x['day']].append(x)
 for f in fills:by_fill[localday(f['execution_at'])].append(f)
 assert set(by_order)<=set(sessions) and set(by_ledger)<=set(sessions) and set(by_fill)<=set(sessions)
 omap={o['order_id']:o for o in orders};assert len(omap)==len(orders)
 expected_orders={}
 for i in intents:
  assert i['as_of']==at(localday(i['as_of']),'15:05:00')
  for d in i['decisions']:
   did=digest({'decision':d,'snapshot':i['snapshot_sha256']});expiry=at(i['execution_session'],'09:30:00')
   oid=digest({'decision_id':did,'at':i['as_of'],'expires_at':expiry})
   assert oid not in expected_orders
   expected_orders[oid]={'order_id':oid,'decision_id':did,'submitted_at':i['as_of'],'eligible_at':expiry,'expires_at':expiry,
    **{k:d[k] for k in ('action','security_id','quantity')}}
 assert set(omap)==set(expected_orders)
 for oid,o in omap.items():
  assert {k:o[k] for k in expected_orders[oid]}==expected_orders[oid]
  assert type(o['quantity']) is int and 0<o['quantity']<=1000000
 fmap={f['order_id']:f for f in fills};assert len(fmap)==len(fills) and set(fmap)<=set(omap)
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
  seen_day=[]
  for o in sorted(by_order[day],key=lambda o:(o['action']!='SELL',o['security_id'])):
   code=o['security_id'];side=o['action'];bar=bars[code][day];q=o['quantity'];assert side in ('BUY','SELL')
   assert bar['tradestatus'] in ('0','1') and bar['isST']=='0'
   blocked=bar['tradestatus']=='0'
   if not blocked:
    price=D(bar['open']);ref=D(bar['preclose']);assert price>0 and price==cents(price)
    blocked=price>=ref*D('1.095') if side=='BUY' else price<=ref*D('.905')
   if blocked:assert o['status']=='UNFILLED_MARKET_CONSTRAINT' and o['order_id'] not in fmap;continue
   if side=='BUY':
    assert q%100==0;q=min(q,int(cash/price)//100*100)
    while q>0 and price*q+fee(price*q,side,extra)>cash:q-=100
   else:q=min(q,sum(n for n,bought,_ in lots[code] if bought<day))
   if q<=0:assert o['status']=='UNFILLED_CASH_OR_T1' and o['order_id'] not in fmap;continue
   gross=price*q;cost=fee(gross,side,extra)
   if side=='SELL' and cash+gross<cost:
    assert o['status']=='UNFILLED_FEES_CASH' and o['order_id'] not in fmap;continue
   assert o['status']==('FILLED' if q==o['quantity'] else 'PARTIAL_DAY_EXPIRED')
   f=fmap[o['order_id']];assert f['quantity']==q and f['security_id']==code and f['action']==side
   assert f['execution_at']==at(day,'09:30:00') and D(f['price'])==price and D(f['cost'])==cost
   if side=='BUY':cash-=gross+cost;lots[code].append([q,day,price])
   else:
    cash+=gross-cost;left=q
    for lot in lots[code]:
     if lot[1]<day:take=min(left,lot[0]);lot[0]-=take;left-=take
    assert left==0
   lots={c:[ls for ls in items if ls[0]] for c,items in lots.items()};lots=defaultdict(list,{c:ls for c,ls in lots.items() if ls})
   assert cash>=0 and cash==D(f['cash_after']);dayfees+=cost;extra_fees+=cents(gross*D(extra)/10000)
   assert D(bar['volume'])>0;capacity=max(capacity,D(q)/D(bar['volume']));seen_day.append(f);filled_seen.add(o['order_id'])
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
 r24=(nav['2024-12-31']/D('1000000')-1)*100;r25=(nav['2025-12-31']/nav['2024-12-31']-1)*100;exposure=exposure_sum/count*100
 for key,vv in (('2024_return_pct',r24),('2025_return_pct',r25),('average_exposure_pct',exposure),('max_order_fraction_of_whole_day_volume',capacity)):
  assert abs(float(vv)-stated[key])<1e-10
 assert len(fills)==stated['fills'] and len(orders)==stated['orders'] and capacity<=1 and stated['whole_day_volume_violations']==0
 return {'status':'INDEPENDENT_PHYSICAL_DAILY_ACCOUNT_RECONSTRUCTED','source_sessions':486,'account_sessions':count,
  'monthly_intents_and_snapshots_reconstructed':snapshot_count,'record_and_ex_events_reconstructed':255,'corporate_ledger_entries':len(ledger),
  'orders_and_statuses_reconstructed':len(orders),'fills_reconstructed':len(fills),'2024_return_pct':float(r24),'2025_return_pct':float(r25),
  'average_exposure_pct':float(exposure),'max_drawdown_pct':float(dd*100),'ending_equity_CNY':str(nav[sessions[-1]]),
  'total_fees_CNY':str(total_fees),'extra_fees_CNY':str(extra_fees),'gross_dividends_CNY':str(gross_div),'flat_stress_tax_CNY':str(tax)}

results={};cases={}
for extra,stated in summary['results_by_extra_bps'].items():
 cases[extra]=load_case(root/extra,stated);results[extra]=audit(cases[extra],int(extra),stated)
negatives={}
for name in ('erased_fee','false_daily_equity','false_record_quantity','wrong_target_quantity','wrong_order_status','allocation_receipt_budget'):
 v=copy.deepcopy(cases['40'])
 if name=='erased_fee':v['fills'][0]['cost']='0'
 elif name=='false_daily_equity':v['rows'][-1]['equity']=str(D(v['rows'][-1]['equity'])+1)
 elif name=='false_record_quantity':next(x for x in v['corporate_ledger'] if x['kind']=='RECORD_DATE_OWNERSHIP')['quantity']+=100
 elif name=='wrong_target_quantity':v['intents'][0]['decisions'][0]['quantity']+=100
 elif name=='wrong_order_status':
  o=v['orders'][0];o['status']='UNFILLED_MARKET_CONSTRAINT' if o['status']=='FILLED' else 'FILLED'
 else:v['intents'][0]['allocation_receipt']['target_notional_budget']+=100
 try:audit(v,40,summary['results_by_extra_bps']['40'])
 except (AssertionError,KeyError):negatives[name]=True
 else:raise AssertionError('arithmetic negative control accepted: '+name)
ref=results['40'];passes=min(ref['2024_return_pct'],ref['2025_return_pct'])>0 and ref['average_exposure_pct']>=90
assert passes==summary['raw_daily_proxy_development_gate_passes']
result={'status':'SEPARATE_STDLIB_COMPOSITE_RAW_DAILY_ACCOUNT_AUDIT_COMPLETE','audit_code_sha256':sha(__file__),
 'audit_authorship':'ROOT_AUTHORED_SEPARATE_ALGORITHM_FROM_RUNTIME','plan_sha256':sha(planfile),'summary_sha256':sha(root/'summary.json'),'imports_project_code':False,
 'results_by_extra_bps':results,'arithmetic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,
 'raw_daily_proxy_development_gate_passes_independently':passes,'minute_execution_admitted':False,
 'historical_arrival_certified':False,'full_corporate_actions_certified':False,'actual_FIFO_tax_liability_verified':False,
 'queue_and_impact_calibrated':False,'2026_return_computed':False,'new_2026_queries':False,'candidate_promoted':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('Both physical daily profiles reconstructed, all orders,24snapshots,255events and48budgetedpriorcloseallocations;6 arithmetic negatives rejected')
