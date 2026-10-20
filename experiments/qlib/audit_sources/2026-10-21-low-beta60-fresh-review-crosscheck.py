import json,csv,copy,hashlib
from pathlib import Path
from decimal import Decimal as D,ROUND_HALF_UP,ROUND_DOWN
from collections import defaultdict
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
P=B/'low-beta60-raw-daily-development-20261021'
read=lambda p:json.loads(p.read_text())
q=lambda n:n.quantize(D('.01'),rounding=ROUND_HALF_UP)
summary=read(P/'summary.json');events=read(B/'low-beta60-account-source-events-20261021/derived_events.json')
sessions=read(B/'low-beta60-raw-dev-20261021/calendar.json')['sessions']
targets=read(B/'low-beta60-pre2026-formations-20261021/targets.json')['low_beta60']
manifest=read(B/'low-beta60-raw-dev-20261021/manifest.json')
bars={code:{r['date']:r for r in read(B/'low-beta60-raw-dev-20261021/codes'/(code+'.json'))['bars']} for code in manifest['per_code_sha256']}
def verify(bps,data):
 days,fills,ledger,own,intents,orders=data
 assert [r['day'] for r in days]==sessions and list(own)==sessions
 nav={r['day']:D(r['equity']) for r in days}
 r=summary['results_by_extra_bps'][str(bps)]
 assert float((nav['2024-12-31']/D('1000000')-1)*100)==r['2024_return_pct']
 assert float((nav['2025-12-31']/nav['2024-12-31']-1)*100)==r['2025_return_pct']
 by_kind=defaultdict(list)
 for l in ledger:by_kind[(l['event_id'],l['kind'])].append(l)
 additions=defaultdict(list);payments=defaultdict(list);claims=[];pending=[]
 expected_entries=0
 for e in events:
  eid,code=e['event_id'],e['instrument'];n=own[e['recorded']].get(code,0)
  rec=by_kind[(eid,'RECORD_DATE_OWNERSHIP')];ex=by_kind[(eid,'EX_DATE_ENTITLEMENT')]
  assert rec==[{'day':e['recorded'],'kind':'RECORD_DATE_OWNERSHIP','event_id':eid,'instrument':code,'quantity':n}]
  gross=q(D(e['cash_per_share'])*n);taxable=q(D(e['stock_taxable_income_per_share'])*n);reserve=q((gross+taxable)*D('.2'))
  cs=D(e['capital_per_share'])*n;ss=D(e['stock_per_share'])*n
  assert cs==int(cs) and ss==int(ss)
  assert ex==[{'day':e['ex_date'],'kind':'EX_DATE_ENTITLEMENT','event_id':eid,'instrument':code,'registered_quantity':n,'cash_gross':str(gross),'stress_tax_reserve':str(reserve),'capital_shares':int(cs),'stock_shares':int(ss),'taxable_stock_income':str(taxable)}]
  expected_entries+=2
  if gross:
   paid=next((day for day in sessions if day>e['pay_date']),None);net=gross-reserve
   assert by_kind[(eid,'NET_DIVIDEND_CASH_AVAILABLE')]==[{'day':paid,'kind':'NET_DIVIDEND_CASH_AVAILABLE','event_id':eid,'cash_delta':str(net)}]
   payments[paid].append(net);claims.append((e['ex_date'],paid,net));expected_entries+=1
  for quantity,kind in [(cs,'CAPITAL_SHARES_LISTED'),(ss,'STOCK_DIVIDEND_SHARES_LISTED')]:
   if quantity:
    assert by_kind[(eid,kind)]==[{'day':e['listed'],'kind':kind,'event_id':eid,'quantity':int(quantity)}]
    additions[e['listed']].append((code,int(quantity)));pending.append((code,e['ex_date'],e['listed'],quantity));expected_entries+=1
 assert expected_entries==len(ledger)
 by_day=defaultdict(list)
 for f in fills:by_day[f['execution_at'][:10]].append(f)
 cash=D('1000000');positions={};prior=cash;marks={};peak=cash;dd=D(0);exposures=[]
 order_map={o['order_id']:o for o in orders};assert len(order_map)==len(orders)
 for row in days:
  day=row['day'];div=sum(payments[day],D(0));cash+=div;fees=D(0)
  for code,n in additions[day]:positions[code]=positions.get(code,0)+n
  for f in by_day[day]:
   code=f['security_id'];price=D(f['price']);n=f['quantity'];o=order_map[f['order_id']]
   assert f['execution_at']==o['eligible_at']==o['expires_at'] and o['submitted_at']<f['execution_at']
   assert 0<n<=o['quantity'] and (f['action']!='BUY' or n%100==0)
   assert price==D(bars[code][day]['open']) and bars[code][day]['tradestatus']=='1'
   gross=price*n;fee=q(max(D(5),gross*D(5 if f['action']=='BUY' else 15)/10000))+q(gross*D(bps)/10000)
   assert D(f['cost'])==fee;fees+=fee
   sign=1 if f['action']=='BUY' else -1;cash-=sign*gross+fee;positions[code]=positions.get(code,0)+sign*n
   assert positions[code]>=0 and cash>=0 and cash==D(f['cash_after'])
   if not positions[code]:del positions[code]
  assert positions==own[day]
  for code in bars:
   bar=bars[code][day]
   if bar['tradestatus']=='1':marks[code]=D(bar['close'])
   elif any(e['ex_date']==day and e['instrument']==code for e in events):marks[code]=D(bar['preclose'])
   elif code not in marks and bar['close'] and D(bar['close'])>0:marks[code]=D(bar['close'])
  market=sum((n*marks[c] for c,n in positions.items()),D(0))
  receivable=sum((net for ex,pay,net in claims if ex<=day<pay),D(0))
  pending_value=sum((n*marks[c] for c,ex,listed,n in pending if ex<=day<listed),D(0))
  equity=cash+market+receivable+pending_value;exposure=(market+pending_value)/equity
  checks={'cash':cash,'market_value':market,'cash_receivable':receivable,'pending_stock_value':pending_value,'equity':equity,'fees':fees,'net_dividend_cash_available':div,'net_return':equity/prior-1,'exposure':exposure}
  for key,value in checks.items():assert D(row[key])==value,(bps,day,key)
  prior=equity
  if day>='2024-01-02':exposures.append(exposure);peak=max(peak,equity);dd=min(dd,equity/peak-1)
 assert float(sum(exposures)/len(exposures)*100)==r['average_exposure_pct'] and float(dd*100)==r['max_drawdown_pct']
 assert len(intents)==24 and {i['execution_session'] for i in intents}==set(targets)
 for intent in intents:
  exe=intent['execution_session'];at=targets[exe]['as_of'];weights=targets[exe]['weights'];held=own[at]
  assert sessions[sessions.index(exe)-1]==at and intent['as_of']==at+'T07:05:00+00:00'
  assert D(intent['equity_at_decision'])==nav[at] and intent['owned_integer_shares']==held
  expected=[]
  for code in sorted(set(held)|set(weights)):
   n=held.get(code,0);w=D(weights.get(code,'0'));desired=int((nav[at]*w/D(bars[code][at]['close'])/100).to_integral_value(rounding=ROUND_DOWN))*100 if w else 0
   if desired>n:expected.append(('BUY',code,(desired-n)//100*100))
   elif desired<n:expected.append(('SELL',code,n-desired))
  expected=sorted([x for x in expected if x[2]],key=lambda x:(x[0]!='SELL',x[1]))
  actual=[(d['action'],d['security_id'],d['quantity']) for d in intent['decisions']]
  assert actual==expected
 return {'sessions':len(days),'events':len(events),'ledger_entries':len(ledger),'fills':len(fills),'orders':len(orders),'intents':len(intents),'annual_returns':[r['2024_return_pct'],r['2025_return_pct']]}
results={}
for bps in (20,40):
 folder=P/str(bps);days=list(csv.DictReader((folder/'daily.csv').open()))
 data=[days]+[read(folder/(n+'.json')) for n in ('fills','corporate_ledger','ownership','intents','orders')]
 results[str(bps)]=verify(bps,data)
 for kind in ('fee','cash','entitlement','decision'):
  altered=copy.deepcopy(data)
  if kind=='fee':altered[1][0]['cost']=str(D(altered[1][0]['cost'])+D('.01'))
  elif kind=='cash':altered[0][1]['cash']=str(D(altered[0][1]['cash'])+D('.01'))
  elif kind=='entitlement':next(l for l in altered[2] if l['kind']=='EX_DATE_ENTITLEMENT')['registered_quantity']+=1
  else:altered[4][0]['decisions'][0]['quantity']+=100
  try:verify(bps,altered)
  except AssertionError:pass
  else:raise AssertionError('negative accepted: '+kind)
 results[str(bps)]['four_no_hash_negative_controls_rejected']=True
print(json.dumps(results,indent=2))
Path('/tmp/stock-rsi-fresh-review-lowbeta-raw-audit-20261021.json').write_text(json.dumps(results,indent=2)+'\n')
