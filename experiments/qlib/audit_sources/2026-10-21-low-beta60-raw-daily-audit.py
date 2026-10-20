"""Stdlib audit: physical lots, source events, every order and visible snapshot."""
import argparse,copy,csv,hashlib,json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal as D,ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo
p=argparse.ArgumentParser()
for n in ('source-root','run-dir','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);root=Path(a.run_dir);repo=Path(__file__).resolve().parents[3]
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
read=lambda f:json.loads(Path(f).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def cents(v):return v.quantize(D('.01'),rounding=ROUND_HALF_UP)
def at(day,clock):return datetime.fromisoformat(day+'T'+clock+'+08:00').astimezone(ZoneInfo('UTC')).isoformat()
def localday(ts):return datetime.fromisoformat(ts).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
planfile=repo/'experiments/qlib/low-beta60-raw-daily-v2-plan.json'
assert sha(planfile)=='42aa916cfd71b5dd6111fb93b4ab696b11119aaa99746884e9d990dff3fc8516'
plan=read(planfile);summary=read(root/'summary.json')
assert summary['plan_sha256']==sha(planfile) and summary['method_code_sha256']==plan['method_code_sha256']
for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
 for f,h in plan[field].items():assert sha(parent/f)==h
assert sha(repo/plan['protocol_file'])==plan['protocol_sha256']
source=base/'low-beta60-account-source-events-20261021';ss=read(source/'summary.json')
sourceaudit=read(base/'low-beta60-event-source-independent-audit-20261021.json')
assert sourceaudit['summary_sha256']==sha(source/'summary.json') and sourceaudit['events_reconstructed']==179
assert all(sourceaudit['negative_controls_rejected'].values()) and not sourceaudit['imports_project_code']
assert sha(repo/'experiments/qlib/audit_sources/2026-10-21-low-beta60-event-source-audit.py')==sourceaudit['audit_code_sha256']
for f,h in ss['artifact_sha256'].items():assert sha(source/f)==h
raw=base/'low-beta60-raw-dev-20261021';m=read(raw/'manifest.json')
assert sha(raw/'manifest.json')==ss['raw_manifest_sha256']
sessions=read(raw/'calendar.json')['sessions'];assert len(sessions)==486 and sessions==sorted(set(sessions))
assert sessions[0]=='2023-12-29' and sessions[-1]=='2025-12-31' and sha(raw/'calendar.json')==m['calendar_sha256']
bars={}
for c,h in m['per_code_sha256'].items():
 f=raw/'codes'/(c+'.json');assert sha(f)==h;v=read(f)
 assert v['instrument']==c and [r['date'] for r in v['bars']]==sessions
 bars[c]={r['date']:r for r in v['bars']}
tf=base/'low-beta60-pre2026-formations-20261021/targets.json';assert sha(tf)==ss['target_sha256']==m['target_sha256']
targets=read(tf)['low_beta60'];assert len(targets)==24 and len(bars)==69
elist=read(source/'derived_events.json');events={e['event_id']:e for e in elist};assert len(events)==len(elist)==179
assert set(summary['results_by_extra_bps'])=={'20','40'}
for flag in ('minute_execution_admitted','historical_arrival_certified','full_corporate_actions_certified','queue_and_impact_calibrated','actual_FIFO_tax_liability_verified','2026_return_computed','new_2026_queries','candidate_promoted','objective_achieved'):assert summary[flag] is False

def fee(gross,side,extra):return cents(max(D(5),gross*D('.0005' if side=='BUY' else '.0015')))+cents(gross*D(extra)/10000)
def load_case(folder,stated):
 assert stated['status']=='RAW_DAILY_PROXY_RECONCILED'
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
 assert count==485 and snapshot_count==24 and filled_seen==set(fmap) and len(registered)==179
 r24=(nav['2024-12-31']/D('1000000')-1)*100;r25=(nav['2025-12-31']/nav['2024-12-31']-1)*100;exposure=exposure_sum/count*100
 for key,vv in (('2024_return_pct',r24),('2025_return_pct',r25),('average_exposure_pct',exposure),('max_drawdown_pct',dd*100),('max_order_fraction_of_whole_day_volume',capacity)):
  assert abs(float(vv)-stated[key])<1e-10
 assert len(fills)==stated['fills'] and len(orders)==stated['orders'] and capacity<=1 and stated['whole_day_volume_violations']==0
 return {'status':'INDEPENDENT_PHYSICAL_DAILY_ACCOUNT_RECONSTRUCTED','source_sessions':486,'account_sessions':count,
  'monthly_intents_and_snapshots_reconstructed':snapshot_count,'record_and_ex_events_reconstructed':179,'corporate_ledger_entries':len(ledger),
  'orders_and_statuses_reconstructed':len(orders),'fills_reconstructed':len(fills),'2024_return_pct':float(r24),'2025_return_pct':float(r25),
  'average_exposure_pct':float(exposure),'max_drawdown_pct':float(dd*100),'ending_equity_CNY':str(nav[sessions[-1]]),
  'total_fees_CNY':str(total_fees),'extra_fees_CNY':str(extra_fees),'gross_dividends_CNY':str(gross_div),'flat_stress_tax_CNY':str(tax)}

results={};cases={}
for extra,stated in summary['results_by_extra_bps'].items():
 cases[extra]=load_case(root/extra,stated);results[extra]=audit(cases[extra],int(extra),stated)
negatives={}
for name in ('erased_fee','false_daily_equity','false_record_quantity','wrong_target_quantity','unfilled_order_forged_as_filled'):
 v=copy.deepcopy(cases['40'])
 if name=='erased_fee':v['fills'][0]['cost']='0'
 elif name=='false_daily_equity':v['rows'][-1]['equity']=str(D(v['rows'][-1]['equity'])+1)
 elif name=='false_record_quantity':next(x for x in v['corporate_ledger'] if x['kind']=='RECORD_DATE_OWNERSHIP')['quantity']+=100
 elif name=='wrong_target_quantity':v['intents'][0]['decisions'][0]['quantity']+=100
 else:next(o for o in v['orders'] if o['status']=='UNFILLED_MARKET_CONSTRAINT')['status']='FILLED'
 try:audit(v,40,summary['results_by_extra_bps']['40'])
 except (AssertionError,KeyError):negatives[name]=True
 else:raise AssertionError('arithmetic negative control accepted: '+name)
ref=results['40'];passes=min(ref['2024_return_pct'],ref['2025_return_pct'])>0 and ref['average_exposure_pct']>=90
assert passes==summary['raw_daily_proxy_development_gate_passes']
result={'status':'INDEPENDENT_LOW_BETA60_RAW_DAILY_ACCOUNT_AUDIT_COMPLETE','audit_code_sha256':sha(__file__),
 'plan_sha256':sha(planfile),'summary_sha256':sha(root/'summary.json'),'imports_project_code':False,
 'results_by_extra_bps':results,'arithmetic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,
 'raw_daily_proxy_development_gate_passes_independently':passes,'minute_execution_admitted':False,
 'historical_arrival_certified':False,'full_corporate_actions_certified':False,'actual_FIFO_tax_liability_verified':False,
 'queue_and_impact_calibrated':False,'2026_return_computed':False,'new_2026_queries':False,'candidate_promoted':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('Both physical daily profiles reconstructed, all orders,24snapshots,179events;5 arithmetic negatives rejected')
