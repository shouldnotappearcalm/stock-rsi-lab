"""Independent Decimal accounting audit; no project engine/strategy imports."""
import argparse,csv,hashlib,json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal as D,ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

p=argparse.ArgumentParser()
for n in ('source-root','replay-dir','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);root=Path(a.replay_dir);repo=Path(__file__).resolve().parents[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
cents=lambda v:v.quantize(D('.01'),rounding=ROUND_HALF_UP)
summary=read(root/'summary.json');planpath=repo/'experiments/qlib/budgeted-residual-capital-income-stress-development-plan.json';plan=read(planpath)
assert sha(planpath)==summary['plan_sha256']
assert summary['status']=='COUNTERFACTUAL_FULL_CAPITAL_INCOME_TAX_STRESS'
for field,folder in [('method_code_sha256',repo),('local_source_sha256',base),('public_evidence_sha256',repo)]:
 for name,h in plan[field].items():assert not Path(name).is_absolute() and '..' not in Path(name).parts and sha(folder/name)==h,(field,name)
assert summary['method_code_sha256']==plan['method_code_sha256']
for flag in ('raw_daily_proxy_development_gate_passes','raw_source_admitted_for_account_replay','actual_tax_exemption_certified','actual_tax_settlement_reproduced','actual_net_return_lower_bound','minute_execution_admitted','historical_arrival_certified','candidate_promoted','objective_achieved'):
 assert summary[flag] is False,flag
raw=base/'budgeted-residual-raw-dev-20261021';manifest=read(raw/'manifest.json')
assert sha(raw/'calendar.json')==manifest['calendar_sha256']
sessions=read(raw/'calendar.json')['sessions'];assert len(sessions)==486 and [sessions[0],sessions[-1]]==['2023-12-29','2025-12-31']
packets={}
for code,h in manifest['per_code_sha256'].items():
 path=raw/'codes'/(code+'.json');assert sha(path)==h
 packet=read(path);assert packet['instrument']==code and [r['date'] for r in packet['bars']]==sessions
 packets[code]=packet
assert len(packets)==210
bars={c:{r['date']:r for r in v['bars']} for c,v in packets.items()}
events={e['event_id']:e for e in read(base/'budgeted-residual-account-source-events-20261021/derived_events.json')};assert len(events)==510
targets=read(base/'budgeted-residual-development-targets-20261021.json');assert len(targets)==24
registry=read(repo/plan['par_registry']);basis=registry['events'][0]
assert len(registry['events'])==1 and basis['event_id']==plan['scenario_event_id']
par=D(basis['par_value_CNY']);assert par==1 and D(basis['nominal_capital_CNY'])==par*basis['ordinary_shares']
assert all(s['publication_day']=='2025-04-26' and sha(base/s['file'])==s['sha256'] for s in basis['sources'])
scenario=basis['event_id'];assert events[scenario]['capital_tax_exempt_verified'] is False
controls=read(root/'both_original_prefix_controls.json');assert controls==summary['both_original_prefix_controls'] and set(controls)=={'20','40'}
results={}
for cost in ['20','40']:
 stated=summary['results_by_extra_bps'][cost];assert stated['status']=='COUNTERFACTUAL_COMPLETE_UNAUDITED'
 folder=root/cost
 for name,h in stated['artifact_sha256'].items():assert Path(name).name==name and sha(folder/name)==h
 assert set(f.name for f in folder.iterdir())==set(stated['artifact_sha256'])
 prefix=read(folder/'original_prefix_receipt.json');assert prefix==stated['original_prefix_receipt']==[controls[cost]]
 assert controls[cost]['original_failure_bytes_reproduced'] is True and controls[cost]['account_prefix_sha256']==plan['original_failed_prefix_sha256'][cost]
 old=read(base/f'budgeted-residual-raw-daily-development-20261021/{cost}/failed_account_state.json')
 fills=read(folder/'fills.json');ledger=read(folder/'corporate_ledger.json');ownership=read(folder/'ownership.json');intents=read(folder/'intents.json');orders=read(folder/'orders.json')
 dayof=lambda f:datetime.fromisoformat(f['execution_at']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
 assert [f for f in fills if dayof(f)<'2025-06-27']==old['fills']
 assert [r for r in ledger if r['day']<'2025-06-27']==old['corporate_ledger']
 rows=list(csv.DictReader((folder/'daily.csv').open()));assert [r['day'] for r in rows]==sessions and set(ownership)==set(sessions)
 byfill=defaultdict(list);byledger=defaultdict(list)
 for f in fills:byfill[dayof(f)].append(f)
 for r in ledger:byledger[r['day']].append(r)
 intentbyday={datetime.fromisoformat(i['as_of']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat():i for i in intents};assert len(intentbyday)==len(intents)==24
 cash=D('1000000');lots=defaultdict(list);claims={};pending={};registered={};nav={};marks={};previous=D('1000000')
 totalfees=D(0);totalreserve=D(0);totalcapitalincome=D(0);totaladditional=D(0);totalcashgross=D(0);exposures=[];maxcapacity=D(0);stress=[]
 for number,row in enumerate(rows):
  day=row['day'];entries=byledger[day];paid=D(0);dayfee=D(0)
  assert all(r['kind'] in {'NET_DIVIDEND_CASH_AVAILABLE','EX_DATE_ENTITLEMENT','CAPITAL_SHARES_LISTED','STOCK_DIVIDEND_SHARES_LISTED','RECORD_DATE_OWNERSHIP'} for r in entries)
  payrows=[r for r in entries if r['kind']=='NET_DIVIDEND_CASH_AVAILABLE'];due={k for k,(at,net) in claims.items() if at==day}
  assert {r['event_id'] for r in payrows}==due and len(payrows)==len(due)
  for r in payrows:
   at,net=claims.pop(r['event_id']);assert D(r['cash_delta'])==net
   cash+=net;paid+=net
  exrows=[r for r in entries if r['kind']=='EX_DATE_ENTITLEMENT'];expectedex={k for k,e in events.items() if e['ex_date']==day}
  assert {r['event_id'] for r in exrows}==expectedex and len(exrows)==len(expectedex)
  for r in exrows:
   k=r['event_id'];e=events[k];q=registered.get(k,0);capital=D(e['capital_per_share'])*q;stock=D(e['stock_per_share'])*q
   assert capital==int(capital) and stock==int(stock) and r['registered_quantity']==q
   gross=cents(D(e['cash_per_share'])*q);stockincome=cents(D(e['stock_taxable_income_per_share'])*q);capitalincome=D(0)
   if q and capital and e['capital_tax_exempt_verified'] is not True:
    assert k==scenario;capitalincome=cents(capital*par)
   if q and stock:assert e['stock_tax_basis_verified'] is True and stockincome>0
   reserve=cents((gross+stockincome+capitalincome)*D('.2'));assert reserve<=gross
   assert (D(r['cash_gross']),D(r['stress_tax_reserve']),r['capital_shares'],r['stock_shares'],D(r['taxable_stock_income']))==(gross,reserve,int(capital),int(stock),stockincome)
   assert D(r.get('taxable_capital_stress_income','0'))==capitalincome
   if gross:claims[k]=(next((d for d in sessions if d>e['pay_date']),None),gross-reserve)
   for quantity,kind in [(capital,'CAPITAL_TRANSFER'),(stock,'STOCK_DIVIDEND')]:
    if quantity:pending[(k,kind)]=(e['instrument'],int(quantity),e['listed'],e['recorded'])
   totalcashgross+=gross;totalreserve+=reserve;totalcapitalincome+=capitalincome
   if capitalincome:
    extra=reserve-cents((gross+stockincome)*D('.2'));totaladditional+=extra
    stress.append({'event_id':k,'registered_quantity':q,'capital_income':str(capitalincome),'combined_reserve':str(reserve),'additional_reserve':str(extra)})
  creditrows=[r for r in entries if r['kind'] in ('CAPITAL_SHARES_LISTED','STOCK_DIVIDEND_SHARES_LISTED')]
  expectedcredits={k for k,(c,q,at,record) in pending.items() if at<=day}
  actualcredits={(r['event_id'],'CAPITAL_TRANSFER' if r['kind']=='CAPITAL_SHARES_LISTED' else 'STOCK_DIVIDEND') for r in creditrows}
  assert actualcredits==expectedcredits and len(creditrows)==len(expectedcredits)
  for r in creditrows:
   kind='CAPITAL_TRANSFER' if r['kind']=='CAPITAL_SHARES_LISTED' else 'STOCK_DIVIDEND'
   code,q,at,record=pending.pop((r['event_id'],kind));assert r['quantity']==q;lots[code].append([q,record])
  for f in byfill[day]:
   code=f['security_id'];q=f['quantity'];source=bars[code][day];price=D(f['price']);assert type(q) is int and 0<q<=1000000
   assert source['tradestatus']=='1' and source['isST']=='0' and price==D(source['open']) and price==cents(price)
   gross=price*q;fee=cents(max(D(5),gross*D('.0005' if f['action']=='BUY' else '.0015')))+cents(gross*D(cost)/10000)
   assert fee==D(f['cost'])
   if f['action']=='BUY':
    assert q%100==0 and price<D(source['preclose'])*D('1.095');cash-=gross+fee;lots[code].append([q,day])
   else:
    assert f['action']=='SELL' and price>D(source['preclose'])*D('.905') and sum(n for n,at in lots[code] if at<day)>=q
    left=q
    for lot in lots[code]:
     if lot[1]>=day:continue
     take=min(left,lot[0]);lot[0]-=take;left-=take
    assert left==0;cash+=gross-fee
   assert cash>=0 and cash==D(f['cash_after']);dayfee+=fee;maxcapacity=max(maxcapacity,D(q)/D(source['volume']))
  quantities={c:sum(q for q,at in ls) for c,ls in lots.items() if sum(q for q,at in ls)};assert ownership[day]==quantities
  recordrows=[r for r in entries if r['kind']=='RECORD_DATE_OWNERSHIP'];expectedrecord={k for k,e in events.items() if e['recorded']==day}
  assert {r['event_id'] for r in recordrows}==expectedrecord and len(recordrows)==len(expectedrecord)
  for r in recordrows:
   e=events[r['event_id']];q=quantities.get(e['instrument'],0);assert r['quantity']==q;registered[r['event_id']]=q
  for code,byday in bars.items():
   source=byday[day]
   if source['tradestatus']=='1':marks[code]=D(source['close'])
   elif any(e['instrument']==code and e['ex_date']==day for e in events.values()):marks[code]=D(source['preclose'])
   elif code not in marks and source['close'] and D(source['close'])>0:marks[code]=D(source['close'])
  market=sum((q*marks[c] for c,q in quantities.items()),D(0));pendingvalue=sum((q*marks[c] for c,q,at,rec in pending.values()),D(0));receivable=sum((net for at,net in claims.values()),D(0))
  equity=cash+market+pendingvalue+receivable
  assert (cash,market,pendingvalue,receivable,equity,dayfee,paid)==tuple(D(row[k]) for k in ('cash','market_value','pending_stock_value','cash_receivable','equity','fees','net_dividend_cash_available')),(cost,day,'cash/share/claim valuation')
  assert D(row['net_return'])==equity/previous-1 and D(row['exposure'])==(market+pendingvalue)/equity
  if day>='2024-01-02':exposures.append((market+pendingvalue)/equity)
  if day in intentbyday:
   intent=intentbyday[day];following=sessions[number+1];assert intent['execution_session']==following and targets[following]['as_of']==day and D(intent['equity_at_decision'])==equity
   owned=dict(quantities)
   for c,q,at,rec in pending.values():owned[c]=owned.get(c,0)+q
   assert intent['owned_integer_shares']==owned
   rebuilt=dict(owned)
   for d in intent['decisions']:rebuilt[d['security_id']]=rebuilt.get(d['security_id'],0)+d['quantity']*(1 if d['action']=='BUY' else -1)
   post=intent['allocation_receipt']['post_order_normalized_positions']
   assert {c:q for c,q in rebuilt.items() if q}=={c:int(q) for c,q in post.items() if q}
   assert all(float(q)==int(q) for q in post.values())
  nav[day]=equity;previous=equity;totalfees+=dayfee
 r24=(nav['2024-12-31']/D('1000000')-1)*100;r25=(nav['2025-12-31']/nav['2024-12-31']-1)*100;exposure=sum(exposures)/len(exposures)*100
 assert abs(float(r24)-stated['2024_return_pct'])<1e-10 and abs(float(r25)-stated['2025_return_pct'])<1e-10 and abs(float(exposure)-stated['average_exposure_pct'])<1e-10
 assert abs(float(maxcapacity)-stated['max_order_fraction_of_whole_day_volume'])<1e-15 and maxcapacity<=1
 extra=read(folder/'capital_stress_ledger.json');assert extra==stated['capital_stress_ledger'] and len(extra)==1
 assert stress==[{'event_id':scenario,'registered_quantity':1100,'capital_income':'220.00','combined_reserve':'77.00','additional_reserve':'44.00'}]
 assert (D(extra[0]['additional_scenario_reserve_CNY']),D(extra[0]['capital_income_CNY']),D(extra[0]['combined_reserve_CNY']))==(D(44),D(220),D(77))
 assert extra[0]['capital_tax_exempt_verified'] is False
 unknown=[e for e in events.values() if D(e['capital_per_share']) and e['capital_tax_exempt_verified'] is False]
 assert len(unknown)==3 and all(registered[e['event_id']]==(1100 if e['event_id']==scenario else 0) for e in unknown)
 results[cost]={'status':'INDEPENDENT_CONDITIONAL_DECIMAL_LEDGER_RECONSTRUCTED','sessions':len(rows),'fills':len(fills),'events':len(events),'monthly_intent_equity_inventory_and_receipt_reconciled':24,'original_prefix_fill_and_corporate_bytes_reproduced':True,'ending_equity_CNY':str(nav[sessions[-1]]),'total_fees_CNY':str(totalfees),'gross_cash_dividends_CNY':str(totalcashgross),'combined_stress_reserve_CNY':str(totalreserve),'scenario_capital_income_CNY':str(totalcapitalincome),'additional_scenario_reserve_CNY':str(totaladditional),'2024_return_pct':float(r24),'2025_return_pct':float(r25),'average_exposure_pct':float(exposure)}
result={'status':'TWO_COUNTERFACTUAL_LEDGERS_INDEPENDENTLY_RECONSTRUCTED','audit_code_sha256':sha(__file__),'summary_sha256':sha(root/'summary.json'),'plan_sha256':sha(planpath),'results_by_extra_bps':results,'imports_project_engine_or_strategy':False,'original_source_gate_remains_false':True,'opening_auction_or_impact_verified':False,'actual_tax_settlement_reproduced':False,'actual_net_return_lower_bound':False,'candidate_promoted':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n');print('Both conditional ledgers independently reconstructed; original source gate remains false')
