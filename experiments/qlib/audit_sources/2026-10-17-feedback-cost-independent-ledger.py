"""Read-only Decimal reconstruction. Imports no project account/strategy code."""
import csv,hashlib,json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo
BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
ROOT=BASE/'low-risk-feedback-cost-20261017'
DATA=BASE/'low-risk-raw-account-data-20261017'
PROOFS=json.loads((BASE/'low-risk-corporate-proofs-20261017/manifest.json').read_text())
summary=json.loads((ROOT/'summary.json').read_text())
packets={p.stem:json.loads(p.read_text()) for p in (DATA/'codes').glob('*.json')}
bars={code:{r['date']:r for r in p['bars']} for code,p in packets.items()}
sessions=json.loads((DATA/'calendar.json').read_text())['sessions']
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def cents(value):return value.quantize(D('.01'),rounding=ROUND_HALF_UP)
events={}
for code,p in packets.items():
 for r in p['distributions']:
  over=PROOFS.get('cash_overrides',{}).get(code+'|'+r['dividOperateDate'],{})
  cash=D(over.get('cash_per_share',r['dividCashPsBeforeTax']))
  key=digest({'instrument':code,'source_distribution':r,'effective_cash':str(cash)})
  events[key]={'code':code,'record':r['dividRegistDate'],'ex':r['dividOperateDate'],
   'pay':r['dividPayDate'],'list':r['dividStockMarketDate'],'cash':cash,'capital':D(r['dividReserveToStockPs'] or '0')}
targets=json.loads((BASE/'low-risk-goal-2026-20261017/targets.json').read_text())
assert sha(DATA/'manifest.json')==summary['data_manifest_sha256']
assert sha(BASE/'low-risk-corporate-proofs-20261017/manifest.json')==summary['proof_manifest_sha256']
for code,expected in json.loads((DATA/'manifest.json').read_text())['per_code_sha256'].items():assert sha(DATA/'codes'/(code+'.json'))==expected
results={}
cases=[(int(bps),capital,stated) for bps,values in summary['results_by_extra_bps_and_initial_CNY'].items() for capital,stated in values.items()]
for extra_bps,capital,stated in cases:
 case_id=str(extra_bps)+'/'+capital
 folder=ROOT/str(extra_bps)/capital
 if stated['status']=='INVALID_SINGLE_ORDER_LIMIT':
  assert capital=='100000000' and json.loads((folder/'error.json').read_text())==stated
  assert sorted(p.name for p in folder.iterdir())==['error.json']
  results[case_id]={'status':'INVALID_CAPITAL_CASE_PRESERVED','reason':stated['error']}
  continue
 for name,expected in stated['artifact_sha256'].items():assert sha(folder/name)==expected,(capital,name,'changed bytes')
 rows=list(csv.DictReader((folder/'daily.csv').open()))
 assert [r['day'] for r in rows]==sessions
 intents=json.loads((folder/'intents.json').read_text());orders=json.loads((folder/'orders.json').read_text())
 assert all(type(o['quantity']) is int and 0<o['quantity']<=1000000 for o in orders)
 by_intent={datetime.fromisoformat(i['as_of']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat():i for i in intents}
 assert len(by_intent)==len(intents)==34
 fills=json.loads((folder/'fills.json').read_text());ledger=json.loads((folder/'corporate_ledger.json').read_text());ownership=json.loads((folder/'ownership.json').read_text())
 by_fill=defaultdict(list);by_ledger=defaultdict(list)
 for f in fills:by_fill[datetime.fromisoformat(f['execution_at']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()].append(f)
 for item in ledger:by_ledger[item['day']].append(item)
 cash=D(capital);lots=defaultdict(list);marks={};claims={};stockclaims={};registered={};nav={};ex_seen=set();record_seen=set();max_capacity=D(0)
 total_fees=D(0);total_extra_cost=D(0);total_gross_dividend=D(0);total_reserve=D(0);by_year_turnover=defaultdict(lambda:D(0));by_year_fees=defaultdict(lambda:D(0))
 for row in rows:
  day=row['day'];entries=by_ledger[day];day_fee=D(0);paid=D(0)
  # Independently derive each due payment and capital credit, then compare source events.
  expected_pay={key for key,(available,net) in claims.items() if available==day}
  actual_pay=[x for x in entries if x['kind']=='NET_DIVIDEND_CASH_AVAILABLE']
  assert {x['event_id'] for x in actual_pay}==expected_pay and len(actual_pay)==len(expected_pay)
  for item in actual_pay:
   key=item['event_id'];available,net=claims.pop(key);assert D(item['cash_delta'])==net
   cash+=net;paid+=net
  actual_ex=[x for x in entries if x['kind']=='EX_DATE_ENTITLEMENT']
  expected_ex={key for key,e in events.items() if e['ex']==day}
  assert {x['event_id'] for x in actual_ex}==expected_ex and len(actual_ex)==len(expected_ex)
  for item in actual_ex:
   key=item['event_id'];e=events[key];q=registered.get(key,0);gross=cents(e['cash']*q);reserve=cents(gross*D('.2'));bonus=e['capital']*q
   assert bonus==int(bonus) and item['registered_quantity']==q
   assert D(item['cash_gross'])==gross and D(item['stress_tax_reserve'])==reserve and item['capital_shares']==int(bonus)
   if gross:claims[key]=(next((x for x in sessions if x>e['pay']),None),gross-reserve)
   if bonus:stockclaims[key]=(e['code'],int(bonus),e['list'],e['record'])
   total_gross_dividend+=gross;total_reserve+=reserve;ex_seen.add(key)
  expected_stock={key for key,(_,_,at,_) in stockclaims.items() if at<=day}
  actual_stock=[x for x in entries if x['kind']=='CAPITAL_SHARES_LISTED']
  assert {x['event_id'] for x in actual_stock}==expected_stock and len(actual_stock)==len(expected_stock)
  for item in actual_stock:
   code,q,at,record=stockclaims.pop(item['event_id']);assert item['quantity']==q
   lots[code].append([q,record])
  for f in by_fill[day]:
   code=f['security_id'];q=f['quantity'];price=D(f['price']);source=bars[code][day]
   assert type(q) is int and q>0 and source['tradestatus']=='1' and source['isST']=='0'
   assert price==D(source['open']) and price==cents(price)
   gross=price*q;fee=cents(max(D('5'),gross*D('.0005' if f['action']=='BUY' else '.0015')))
   extra=cents(gross*D(extra_bps)/10000);fee+=extra;total_extra_cost+=extra
   assert fee==D(f['cost'])
   if f['action']=='BUY':
    assert q%100==0 and price<D(source['preclose'])*D('1.095');cash-=gross+fee;lots[code].append([q,day])
   else:
    assert f['action']=='SELL' and price>D(source['preclose'])*D('.905')
    assert sum(n for n,at in lots[code] if at<day)>=q
    left=q
    for lot in lots[code]:
     if lot[1]>=day:continue
     take=min(left,lot[0]);lot[0]-=take;left-=take
    assert left==0;cash+=gross-fee
   assert cash>=0 and cash==D(f['cash_after'])
   day_fee+=fee;by_year_turnover[day[:4]]+=gross;by_year_fees[day[:4]]+=fee
   max_capacity=max(max_capacity,D(q)/D(source['volume']))
  quantities={code:sum(q for q,_ in ls) for code,ls in lots.items() if sum(q for q,_ in ls)}
  assert quantities==ownership[day]
  actual_record=[x for x in entries if x['kind']=='RECORD_DATE_OWNERSHIP']
  expected_record={key for key,e in events.items() if e['record']==day}
  assert {x['event_id'] for x in actual_record}==expected_record and len(actual_record)==len(expected_record)
  for item in actual_record:
   e=events[item['event_id']];q=quantities.get(e['code'],0);assert item['quantity']==q
   registered[item['event_id']]=q;record_seen.add(item['event_id'])
  for code,byday in bars.items():
   source=byday[day]
   if source['tradestatus']=='1':marks[code]=D(source['close'])
   elif any(e['code']==code and e['ex']==day for e in events.values()):marks[code]=D(source['preclose'])
   elif code not in marks and source['close'] and D(source['close'])>0:marks[code]=D(source['close'])
  market=sum((q*marks[code] for code,q in quantities.items()),D(0))
  pending=sum((q*marks[code] for code,q,_,_ in stockclaims.values()),D(0))
  receivable=sum((net for _,net in claims.values()),D(0));equity=cash+market+pending+receivable
  assert (cash,market,pending,receivable,equity,day_fee,paid)==tuple(D(row[k]) for k in ('cash','market_value','pending_stock_value','cash_receivable','equity','fees','net_dividend_cash_available')),(capital,day,'daily mismatch')
  if day in by_intent:
   intent=by_intent[day];following=sessions[sessions.index(day)+1]
   assert intent['execution_session']==following and targets[following]['as_of']==day
   assert intent['equity_at_decision']==str(equity)
   owned=dict(quantities)
   for code,q,_,_ in stockclaims.values():owned[code]=owned.get(code,0)+q
   assert intent['owned_integer_shares']==owned
   expected_orders=[];weights=targets[following]['weights']
   for code in sorted(set(owned)|set(weights)):
    held=owned.get(code,0);weight=D(str(weights.get(code,0)))
    if weight==0:
     if held:expected_orders.append(('SELL',code,held))
     continue
    desired=int(equity*weight/marks[code]/100)*100
    if desired>held:
     quantity=(desired-held)//100*100
     if quantity:expected_orders.append(('BUY',code,quantity))
    elif held>desired:expected_orders.append(('SELL',code,held-desired))
   expected_orders.sort(key=lambda item:(item[0]!='SELL',item[1]))
   actual=[(d['action'],d['security_id'],d['quantity']) for d in intent['decisions']]
   assert actual==expected_orders,(case_id,day,'feedback order sizing mismatch')
  nav[day]=equity;total_fees+=day_fee
 r24=(nav['2024-12-31']/D(capital)-1)*100;r25=(nav['2025-12-31']/nav['2024-12-31']-1)*100;r26=(nav['2026-10-16']/nav['2025-12-31']-1)*100
 assert abs(float(r24)-stated['2024_return_pct'])<1e-10 and abs(float(r25)-stated['2025_return_pct'])<1e-10
 assert abs(float(r26)-stated['2026_through_2026-10-16']['net_compound_return_pct'])<1e-10
 assert max_capacity==D(str(stated['max_order_fraction_of_whole_day_volume'])) or abs(float(max_capacity)-stated['max_order_fraction_of_whole_day_volume'])<1e-15
 results[case_id]={'extra_cost_bps':extra_bps,'initial_CNY':capital,'additional_execution_cost_CNY':str(total_extra_cost),'all_34_account_feedback_intents_independently_resized':True,'status':'INDEPENDENT_DECIMAL_RECONSTRUCTION_PASSED','sessions':len(rows),'fills':len(fills),'source_events':len(events),'record_events':len(record_seen),'ex_events':len(ex_seen),'total_fees_CNY':str(total_fees),'gross_entitled_dividends_CNY':str(total_gross_dividend),'flat_stress_tax_reserve_CNY':str(total_reserve),'ending_equity_CNY':str(nav['2026-10-16']),'2024_pct':float(r24),'2025_pct':float(r25),'2026_through_2026_10_16_pct':float(r26),'numeric_user_conditions_met_at_available_cutoff':r24>0 and r25>0 and r26>=10,'2026_gross_traded_CNY':str(by_year_turnover['2026']),'2026_fees_CNY':str(by_year_fees['2026']),'2026_gross_traded_over_starting_equity':str(by_year_turnover['2026']/nav['2025-12-31'])}
result={'status':'ALL_15_VALID_FEEDBACK_LEDGERS_RECONSTRUCTED_5_INVALID_CASES_PRESERVED','audit_script_sha256':sha(Path(__file__)),'replay_summary_sha256':sha(ROOT/'summary.json'),'imports_project_account_code':False,'results_by_cost_and_capital':results,'scope':'Every monthly intent independently recomputed from stressed NAV/stock inventory; every session reconstructed from raw source, fills and corporate notices: T+1 inventory, record/ex/pay/list events, fees, cash-after-fill, all daily assets and compound returns. No original account engine is imported. Opening auction and impact remain unverified.','objective_achieved':False}
output=Path('experiments/qlib/low-risk-feedback-cost-independent-audit.json')
assert len(results)==20 and sum(v['status']=='INDEPENDENT_DECIMAL_RECONSTRUCTION_PASSED' for v in results.values())==15
assert not output.exists();output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
