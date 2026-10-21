"""Independent Decimal audit of six existing price-delay intraday ledgers.
No project imports, production broker/simulate/summarize calls, network or2026.
The arithmetic core below adapts the published independent low-beta auditor,
with policy/event-count substitution and explicit actual-dependency ST proof.
"""
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,timedelta
from decimal import Decimal as D,ROUND_HALF_UP,ROUND_DOWN,ROUND_UP
from zoneinfo import ZoneInfo
import copy,csv,hashlib,json,subprocess
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
O=B/'price-delay-intraday-pre2026-20261021';P=R/'experiments/qlib/price-delay-intraday-plan.json'
REPORT=Path('/tmp/price-delay-intraday-independent-ledger-audit-20261021.json')
EXPECTED='595244be4f34772b05d1ddd6ab2418d0c8666fdc939e038a1eb3b211d3fd0293'
REFERENCE=R/'experiments/qlib/audit_sources/2026-10-21-low-beta60-intraday-development-audit.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def need(v,s):
    if not v:raise AssertionError(s)
def cents(v):return v.quantize(D('.01'),rounding=ROUND_HALF_UP)
def at(day,clock):return datetime.fromisoformat(day+'T'+clock+'+08:00').astimezone(ZoneInfo('UTC')).isoformat()
def localday(ts):return datetime.fromisoformat(ts).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()

def require_ordinary_components(day,components):
    required=set().union(*(set(c) for c in components.values()))
    need(all(bars[c][day]['isST']=='0' for c in required),'actual account required nonordinary source')
    return required

def dependency_guard(day,index,lots,stockclaims,registered,todays_parents,v):
    held={c for c,ls in lots.items() if sum(q for q,_,_ in ls)>0}
    pendingstock={c for c,q,_,_ in stockclaims.values() if q>0}
    pendingparents={p['security_id'] for p in todays_parents}
    nextday=sessions[index+1] if index+1<len(sessions) else None
    nexttarget=set(targets[nextday]['weights']) if nextday in targets else set()
    exowned={e['instrument'] for eid,e in events.items() if e['ex_date']==day and registered.get(eid,0)>0}
    components={'start_circulating_inventory':held,'start_pending_stock_claims':pendingstock,'pending_parent_instructions':pendingparents,'next_session_monthly_target_prices':nexttarget,'positive_registered_ex_entitlements':exowned}
    required=require_ordinary_components(day,components)
    for c,series in bars.items():
        if series[day]['isST']!='1':continue
        need(c not in required,'ST dependency must fail closed')
        v['_reconstructed_scope'].append({'instrument':c,'session':day,'reason':'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT','original_row_present':True,'source_isST':'1','required_by_account':False,'synthetic_price_created':False})
        v['_dependency_evidence'].append({'instrument':c,'day':day,'absence_in_each_reconstructed_component':{key:c not in value for key,value in components.items()},'required_components_sha256':digest({key:sorted(value) for key,value in components.items()}),'required_security_count':len(required),'source_row_unchanged':True})

# Shared read-only tape reconstruction globals are populated in main.
sessions=[];bars={};targets={};events={};ordinary={};capture=None;tape_cache={}
def tape(code,day):
    need(day<='2025-12-31' and bars[code][day]['isST']=='0','no ST/future tape access')
    key=(code,day);name=code+'-'+day+'.json';p=capture/'sessions'/name
    need(name in ordinary and sha(p)==ordinary[name],'recheck tape hash even on cache hit')
    if key in tape_cache:return tape_cache[key]
    packet=read(p);need(packet['instrument']==code and packet['requested_day']==day,'tape identity');rec=packet.get('methods',{}).get('minutes.history',packet);need(rec['status']=='RESPONSE_CAPTURED','tape captured');response=rec['response'];need(response['code']==code[2:] and response['trading_date']==day,'decoded identity')
    points=response['points'];labels=[f'{h:02}:{m:02}' for h in range(16) for m in range(60) if '09:31'<=f'{h:02}:{m:02}'<='11:30' or '13:01'<=f'{h:02}:{m:02}'<='15:00'];need(len(points)==len(labels)==240,'240minute tape')
    for n,(pt,label) in enumerate(zip(points,labels)):
        need(pt['index']==n and pt['time_label']==label and pt['time']==day+'T'+label+':00+08:00' and type(pt['price_milli']) is int and type(pt['volume']) is int and min(pt['price_milli'],pt['volume'])>=0,'minute clock/type')
        need(D(str(pt['price']))==D(pt['price_milli'])/1000,'price projection')
        if pt['volume']:need(pt['price_milli']>0 and pt['price_milli']%10==0 and D(bars[code][day]['low'])<=D(pt['price_milli'])/1000<=D(bars[code][day]['high']),'minute raw price bounds')
    need(D(points[-1]['price_milli'])/1000==D(bars[code][day]['close']),'minute finalclose')
    windows=[]
    for n in range(0,240,5):
        block=points[n:n+5];end=datetime.fromisoformat(block[-1]['time']).astimezone(ZoneInfo('UTC'));start=end-timedelta(minutes=5);prices=[D(x['price_milli'])/1000 for x in block if x['volume']>0]
        windows.append({'start':start.isoformat(),'end':end.isoformat(),'volume':sum(max(0,x['volume']*100-100) for x in block),'buy':max(prices) if prices else None,'sell':min(prices) if prices else None,'evidence':digest({'security_id':code,'day':day,'points':[{'time':x['time'],'volume':x['volume'],'price_milli':x['price_milli']} for x in block]})})
    need(sum(w['volume'] for w in windows)<=D(bars[code][day]['volume']),'whole-day conservative volume')
    tape_cache[key]=windows;return windows

# Adapted independent arithmetic core follows, copied as source for reviewability.
def legal_quantity(remaining,capacity,side):
 cap=min(remaining,capacity,1000000)
 return remaining if side=='SELL' and remaining<=cap else cap//100*100

def fee(gross,side,extra):return cents(max(D(5),gross*D('.0005' if side=='BUY' else '.0015')))+cents(gross*D(extra)/10000)

def audit_case(v,participation,extra,stated):
 v['_reconstructed_scope']=[];v['_dependency_evidence']=[]
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
  dependency_guard(day,index,lots,stockclaims,registered,by_order[day],v)
  marks={c:value for c,value in marks.items() if bars[c][day]['isST']=='0'}
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
   bar=series[day]
   if bar['isST']=='1':continue
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
   record={'record_id':digest({'policy':'price_delay_d1','formation':day,'target':target}),'kind':'frozen_target','available_at':intent['as_of'],'payload':target}
   visible=[record]
   for c in sorted(set(owned)|set(target['weights'])):
    content={'instrument':c,'as_of':day,'known_mark':str(marks[c]),'source_bar':bars[c][day]}
    visible.append({'record_id':digest(content),'kind':'raw_market_state','available_at':intent['as_of'],'payload':content})
   positions={c:{'quantity':quantities[c],'average_price':str(sum(n*price for n,_,price in ls)/quantities[c]),'mark_price':str(marks[c]),'mark_source':'VISIBLE_PRICE'} for c,ls in lots.items() if ls}
   wealth={'cash':str(cash),'positions':positions,'market_value':str(market),'cash_receivable':str(receivable),'pending_stock_value':str(pending),'equity':str(equity)}
   assert digest({'as_of':intent['as_of'],'records':visible,'account':wealth})==intent['snapshot_sha256'],(day,'snapshot')
   assert all(d['evidence_ids']==[record['record_id']] and d['reason']=='frozen monthly price_delay_d1 target, physical-share execution' for d in intent['decisions'])
   snapshot_count+=1
 assert v['_reconstructed_scope']==v['source_scope_audit'] and len(v['_reconstructed_scope'])==241
 assert count==485 and snapshot_count==24 and filled_seen==set(fmap) and len(registered)==378
 assert orders==expected_all_children
 r24=(nav['2024-12-31']/D('1000000')-1)*100;r25=(nav['2025-12-31']/nav['2024-12-31']-1)*100;exposure=exposure_sum/count*100
 for key,vv in (('2024_return_pct',r24),('2025_return_pct',r25),('average_exposure_pct',exposure),('max_drawdown_pct',dd*100),('max_order_fraction_of_whole_day_volume',capacity)):
  assert abs(float(vv)-stated[key])<1e-10
 assert len(fills)==stated['fills'] and len(orders)==stated['child_orders']==stated['orders'] and len(parents)==stated['parent_instructions'] and capacity<=1 and stated['whole_day_volume_violations']==0
 return {'status':'INDEPENDENT_PHYSICAL_INTRADAY_ACCOUNT_RECONSTRUCTED','source_sessions':486,'account_sessions':count,
  'monthly_intents_and_snapshots_reconstructed':snapshot_count,'record_and_ex_events_reconstructed':378,'corporate_ledger_entries':len(ledger),
  'parent_instructions_reconstructed':len(parents),'children_and_statuses_reconstructed':len(orders),'fills_reconstructed':len(fills),'2024_return_pct':float(r24),'2025_return_pct':float(r25),
  'average_exposure_pct':float(exposure),'max_drawdown_pct':float(dd*100),'ending_equity_CNY':str(nav[sessions[-1]]),
  'total_fees_CNY':str(total_fees),'extra_fees_CNY':str(extra_fees),'gross_dividends_CNY':str(gross_div),'flat_stress_tax_CNY':str(tax)}

def main():
 global sessions,bars,targets,events,ordinary,capture
 plan=read(P);summary=read(O/'summary.json');freeze=subprocess.check_output(['git','rev-parse','70e5f8d'],cwd=R,text=True).strip()
 need(sha(P)==EXPECTED==summary['plan_sha256'] and hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(P.relative_to(R))],cwd=R)).hexdigest()==EXPECTED,'frozen plan')
 rawplanfile=R/'experiments/qlib/price-delay-raw-daily-plan.json';rawplan=read(rawplanfile);scopeplan=read(R/'experiments/qlib/price-delay-ordinary-source-scope-plan.json')
 need(sha(rawplanfile)==plan['raw_daily_plan_sha256'],'original daily plan')
 need(set(plan['method_code_sha256'])==set(rawplan['method_code_sha256'])|set(scopeplan['method_code_sha256'])|{'scripts/run_price_delay_intraday_development.py','src/stock_rsi/intraday_broker.py'},'complete34 method scope')
 need(len(plan['public_evidence_sha256'])==7 and len(plan['local_source_sha256'])==5,'exact public/local counts')
 for bound in [plan,rawplan,scopeplan]:
  for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
   for n,h in bound[field].items():
    need(not Path(n).is_absolute() and '..' not in Path(n).parts and sha(root/n)==h,'bound identity '+n)
    if root==R:need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=R)).hexdigest()==h,'frozen blob '+n)
 need(plan['participation_bps']==[100,500,1000] and plan['extra_cost_bps']==[20,40] and plan['initial_CNY']=='1000000' and plan['allocator']=='plan_integer_targets' and plan['account_guard']=='ordinary_source_rows_on' and plan['candidate']=='price_delay_d1' and plan['window']==['2023-12-29','2025-12-31'],'fixed six profile strategy')
 need(summary['method_code_sha256']==plan['method_code_sha256'] and summary['phase']=='dev' and summary['candidate']=='price_delay_d1','summary identity')
 need(set(summary['results_by_profile'])=={f'{p}/{e}' for p in [100,500,1000] for e in [20,40]} and read(O/'case_results.json')==summary['results_by_profile'],'six cases')
 for key in ['historical_arrival_verified','full_corporate_actions_certified','queue_and_impact_calibrated','actual_FIFO_tax_liability_verified','strict_statutory_tax_certification','2026_strategy_returns_queried','candidate_promoted','objective_achieved']:need(summary[key] is False,'claim scope')
 raw=B/'price-delay-raw-dev-20261021';rm=read(raw/'manifest.json');sessions=read(raw/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==plan['window'] and sha(raw/'calendar.json')==rm['calendar_sha256'],'source486calendar')
 for c,h in rm['per_code_sha256'].items():
  p=raw/'codes'/(c+'.json');need(sha(p)==h,'151source hash');v=read(p);need(v['instrument']==c and v['window']==plan['window'] and [r['date'] for r in v['bars']]==sessions,'source pre2026date');bars[c]={r['date']:r for r in v['bars']}
 need(len(bars)==151,'151source names');tf=B/'price-delay-pre2026-formations-20261021/targets.json';need(sha(tf)==rm['target_sha256'],'targethash');targets=read(tf)['price_delay_d1'];need(len(targets)==24,'24targets')
 source=B/'price-delay-account-source-events-20261021';ss=read(source/'summary.json');sourceaudit=read(B/'price-delay-event-source-independent-audit-20261021.json')
 need(sourceaudit['summary_sha256']==sha(source/'summary.json') and sourceaudit['events_reconstructed']==378 and sourceaudit['all378_economics_dates_event_IDs_and_receipts_identical'] is True and not sourceaudit['critical_or_important_findings'],'independent378sourceaudit')
 for n,h in ss['artifact_sha256'].items():need(sha(source/n)==h,'eventsource artifact')
 elist=read(source/'derived_events.json');events={e['event_id']:e for e in elist};need(len(events)==378 and read(O/'derived_events.json')==elist and sha(O/'derived_events.json')==summary['derived_events_sha256']==sha(source/'derived_events.json'),'378events unchanged')
 need(read(O/'event_source_receipts.json')==read(source/'event_source_receipts.json') and sha(O/'event_source_receipts.json')==summary['event_source_receipts_sha256']==sha(source/'event_source_receipts.json'),'all source receipts')
 proof=read(source/'effective_proofs.json');need(len(proof['capital_tax'])==4 and proof['direct_primary_capital_tax_statements']==3 and proof['conditional_capital_tax_inferences']==1 and proof['strict_statutory_capital_tax_certification'] is False,'four limited capitalproofs')
 need({e['instrument']+'|'+e['ex_date'] for e in elist if e['capital_tax_exempt_verified']}==set(proof['capital_tax']),'capitalflags unchanged')
 unknown=next(e for e in elist if e['instrument']=='SH603596' and e['ex_date']=='2024-05-20');need(unknown['capital_tax_exempt_verified'] is False,'unproved taxflag preserved')
 for key,ratio in sourceaudit['primary_cash_supplements'].items():
  code,day=key.split('|');need(D(next(e['cash_per_share'] for e in elist if e['instrument']==code and e['ex_date']==day))==D(ratio),'actual primarycash not reference')
 capture=B/'price-delay-minutes-dev-20261021';cm=read(capture/'manifest.json');scope=B/'price-delay-ordinary-source-scope-20261021';sc=read(scope/'scope.json');sca=read(R/'experiments/qlib/price-delay-ordinary-source-scope-independent-audit.json')
 need(sca['source_scope_sha256']==sha(scope/'scope.json') and sca['source_summary_sha256']==sha(scope/'summary.json') and sca['ordinary_scope_reconstructed'] is True and sca['conditional_account_dependency_proof'] is False and sca['imports_project_code'] is False,'bound ordinary scope only')
 ordinary=sc['ordinary_packet_sha256'];rejected=sc['rejected_packet_sha256'];need(len(ordinary)==2490 and len(rejected)==12 and {**ordinary,**rejected}==cm['per_session_sha256'],'2490ordinary+12rejected retained')
 for fn,h in cm['per_session_sha256'].items():need(sha(capture/'sessions'/fn)==h,'all2502original tapehash')
 ca=read(R/'experiments/qlib/price-delay-minute-capture-independent-audit.json');need(ca['capture_manifest_sha256']==sha(capture/'manifest.json'),'capture audit binding')
 queries={str(p.relative_to(capture)):sha(p) for p in (capture/'queries').rglob('*') if p.is_file()};need(queries==ca['query_artifact_sha256']==sca['query_artifact_sha256'] and len(queries)==2754,'journal source bytes')
 need(read(B/'price-delay-minute-admission-20261021/summary.json')['admitted_for_reconstructed_execution'] is False,'strict original admission stays failed')
 expected_ST=[(c,d) for c in sorted(bars) for d in sorted(bars[c]) if bars[c][d]['isST']=='1'];need(len(expected_ST)==241 and [(r['instrument'],r['day']) for r in sc['nonordinary_source_intervals']]==expected_ST,'all241raw STdays')
 need(sha(REFERENCE)==hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(REFERENCE.relative_to(R))],cwd=R)).hexdigest(),'independent arithmetic reference bound')
 cases={};results={};allhash={};dependency_evidence={}
 for label,stated in summary['results_by_profile'].items():
  folder=O/label;need(set(stated['artifact_sha256'])=={'corporate_ledger.json','daily.csv','fills.json','intents.json','orders.json','ownership.json','parent_instructions.json','source_scope_audit.json'},'eight complete financial artifacts')
  for fn,h in stated['artifact_sha256'].items():need(sha(folder/fn)==h,'all48financialhashes');allhash[label+'/'+fn]=h
  v={k:read(folder/(k+'.json')) for k in ['orders','fills','corporate_ledger','ownership','intents','parent_instructions','source_scope_audit']}
  with (folder/'daily.csv').open() as f:v['rows']=list(csv.DictReader(f))
  cases[label]=v;participation,extra=map(int,label.split('/'));results[label]=audit_case(v,participation,extra,stated)
  unproved=[r for r in v['corporate_ledger'] if r['event_id']==unknown['event_id'] and r['kind']=='RECORD_DATE_OWNERSHIP'];need(len(unproved)==1 and unproved[0]['day']=='2024-05-17' and unproved[0]['quantity']==0 and unproved==stated['unproved_noncash_record_ownership'],'actual0unproved entitlement')
  need([(x['instrument'],x['session']) for x in v['_reconstructed_scope']]==expected_ST,'6x241account guard rows')
  need(all(all(vv is True for vv in e['absence_in_each_reconstructed_component'].values()) for e in v['_dependency_evidence']),'each dependency component proves absent')
  dailyvolume=defaultdict(int)
  for f in v['fills']:dailyvolume[(f['security_id'],localday(f['execution_at']))]+=f['quantity'];need(f['action']!='BUY' or f['quantity']%100==0,'all100sharebuys')
  need(all(D(q)<=D(bars[c][d]['volume']) for (c,d),q in dailyvolume.items()),'aggregate perissuerday volume')
  unfilled=[p for p in v['parent_instructions'] if p['remaining']>0];need(len(unfilled)==stated['unfilled_parents']==3,'3unfilledparents retained')
  need(stated['ordinary_dependency_guard_passes'] is True and stated['unused_ST_intervals_verified']==241 and stated['all_children_within_1million_shares'] is True,'actual account scoped execution proof')
  results[label].update({'unfilled_parents_retained':unfilled,'unproved_SH603596_May17_record_quantity':0,'ordinary_source_dependency_intervals_reconstructed':241,'ordinary_dependency_guard_passes_independently':True,'aggregate_whole_day_volume_passes':True})
  dependency_evidence[label]=v['_dependency_evidence'];print('Independent audit complete',label,'cash/inventory/378events/24snapshots/allchildren/ST241',flush=True)
 need(len(tape_cache)==summary['tape_accessed_pairs']==953 and all(c+'-'+d+'.json' in ordinary for c,d in tape_cache),'all953accesses ordinary only')
 negatives={};stated=summary['results_by_profile']['100/40']
 for name in ['erased_fee','false_daily_equity','false_record_quantity','wrong_target_quantity','wrong_previous_window_volume','unfilled_child_forged_filled','ST_scope_row_erased']:
  v=copy.deepcopy(cases['100/40'])
  if name=='erased_fee':v['fills'][0]['cost']='0'
  elif name=='false_daily_equity':v['rows'][-1]['equity']=str(D(v['rows'][-1]['equity'])+1)
  elif name=='false_record_quantity':next(x for x in v['corporate_ledger'] if x['kind']=='RECORD_DATE_OWNERSHIP')['quantity']+=100
  elif name=='wrong_target_quantity':v['intents'][0]['decisions'][0]['quantity']+=100
  elif name=='wrong_previous_window_volume':v['orders'][0]['source_volume_lower_shares']+=100
  elif name=='unfilled_child_forged_filled':next(o for o in v['orders'] if o['status'].startswith('UNFILLED'))['status']='FILLED'
  else:v['source_scope_audit'].pop()
  try:audit_case(v,100,40,stated)
  except (AssertionError,KeyError):negatives[name]=True
  else:raise AssertionError('arithmetic source mutation accepted '+name)
 for kind in ['start_circulating_inventory','start_pending_stock_claims','pending_parent_instructions','next_session_monthly_target_prices','positive_registered_ex_entitlements']:
  try:require_ordinary_components('2024-06-03',{kind:{'SZ002092'}})
  except AssertionError:negatives['required_ST_'+kind]=True
  else:raise AssertionError('required ST dependency accepted')
 passes=all(min(results[f'{p}/40']['2024_return_pct'],results[f'{p}/40']['2025_return_pct'])>0 and results[f'{p}/40']['average_exposure_pct']>=90 and results[f'{p}/40']['ordinary_dependency_guard_passes_independently'] for p in [100,500,1000]);need(passes==summary['raw_development_confirmation_passes'],'allthree40bpgate')
 for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
  for n,h in plan[field].items():need(sha(root/n)==h,'all frozen inputs unchanged after audit')
 need(sha(P)==EXPECTED and queries=={str(p.relative_to(capture)):sha(p) for p in (capture/'queries').rglob('*') if p.is_file()},'plan/querybytes unchanged')
 report={'status':'INDEPENDENT_SIX_PRICE_DELAY_INTRADAY_ACCOUNT_LEDGERS_RECONSTRUCTED','summary_sha256':sha(O/'summary.json'),'all_six_profile_ledgers_reconstructed':True,'development_confirmation_passes_independently':passes,'imports_project_code':False,'audit_code_sha256':sha(Path(__file__)),'plan_sha256':EXPECTED,'freeze_commit':freeze,'method_code_sha256':plan['method_code_sha256'],'all48_financial_artifact_sha256':allhash,'source_event_audit_sha256':sha(B/'price-delay-event-source-independent-audit-20261021.json'),'source_scope_audit_sha256':sha(R/'experiments/qlib/price-delay-ordinary-source-scope-independent-audit.json'),'independent_arithmetic_reference':{'file':str(REFERENCE.relative_to(R)),'sha256':sha(REFERENCE),'adaptations':['Policyidentifier changed fromlow_beta60 toprice_delay_d1;eventcount179to378.','Added actual start-day dependency reconstruction and ST mark exclusion; all241auditrows compared.'],'production_code_imported':False},'results_by_profile':results,'actual_account_ST_dependency_evidence_by_profile':dependency_evidence,'all_six_times241_source_scope_rows_reconstructed':True,'all_144_intents_and_full_snapshots_reconstructed':True,'all_parents_children_fills_previous_current_bucket_evidence_reconstructed':True,'all_side_fees_and_no_same_bucket_sale_budget_reconstructed':True,'all378_record_ex_pay_listed_event_entries_reconstructed_per_profile':True,'all6_unknown_SH603596_record_quantities_zero_and_taxflag_false':True,'four_capital_flags_evidence_level':{'direct_statements':3,'conditional_inference':1,'strict_statutory_certification':False},'reconstructed_accessed_minute_pairs':len(tape_cache),'all953_accesses_ordinary_only_and_hash_rechecked_on_cache_hits':True,'original_failed2502_admission_preserved':True,'rejected12ST_packet_hashes_preserved':rejected,'semantic_negative_controls_rejected':negatives,'negative_controls_use_only_hash_gate':False,'account_replay_rerun':False,'portfolio_returns_independently_recomputed_from_existing_pre2026_ledgers':True,'new_2026_values_read':False,'network_calls':0,'repository_or_source_outputs_modified':False,'historical_arrival_verified':False,'full_corporate_actions_certified':False,'actual_FIFO_tax_liability_verified':False,'queue_and_impact_calibrated':False,'strict_statutory_tax_certification':False,'candidate_promoted':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['Allsixpre2026 existing account ledgers independently reconstructed using normalized-minute conservative5minute extrema/hand-volume lowerbounds; this is reconstructed execution evidence, not real exchange fills.','Original2502source admission stays failed; no rejectedSTtape was used. Account-specific absence is proven for the actual frozen six continuous ledgers, not a general relaxation of source rules.','Cash+bonus20%stress reserve remains conditional and is not actual FIFO dividend tax settlement. FIFO share availability is checked independently.','No2026strategy evidence, historical PIT/arrival, exact per-minute share precision, opening depth, queue/impact or full corporate-action certification is established.']}
 REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(REPORT),'report_sha256':sha(REPORT),'script_sha256':report['audit_code_sha256'],'six_ledgers':True,'financial_artifacts':len(allhash),'ST_interval_proofs':6*241,'negative_controls':len(negatives),'development_confirmation':passes}))
if __name__=='__main__':main()
