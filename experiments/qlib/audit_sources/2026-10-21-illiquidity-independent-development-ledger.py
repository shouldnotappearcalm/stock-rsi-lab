"""Read-only Decimal reconstruction. Imports no project account/strategy code."""
import argparse,csv,hashlib,json
from collections import defaultdict
from datetime import datetime,timedelta
from decimal import Decimal as D, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP
from pathlib import Path
from zoneinfo import ZoneInfo
BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
parser=argparse.ArgumentParser();parser.add_argument('--run-dir',required=True);parser.add_argument('--plan',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
ROOT=Path(args.run_dir)
PLAN=json.loads(Path(args.plan).read_text())
DATA=BASE/'illiquidity-raw-source-continuation-20261020'
PROOF_DIR=BASE/'illiquidity-corporate-reviewed-20261020'
PROOFS=json.loads((PROOF_DIR/'reviewed-manifest.json').read_text())
summary=json.loads((ROOT/'summary.json').read_text())
packets={p.stem:json.loads(p.read_text()) for p in (DATA/'codes').glob('*.json')}
bars={code:{r['date']:r for r in p['bars']} for code,p in packets.items()}
sessions=[day for day in json.loads((DATA/'calendar.json').read_text())['sessions'] if day<=summary['end']]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def cents(value):return value.quantize(D('.01'),rounding=ROUND_HALF_UP)
tape_index={};tape_cache={}
for name,expected in (('tdx-fixed-order-history-20261017',PLAN['old_tape_manifest_sha256']),('illiquidity-minutes-dev-20261021',PLAN['extra_tape_manifest_sha256'])):
 source=BASE/name;assert sha(source/'manifest.json')==expected
 for filename,expected_hash in json.loads((source/'manifest.json').read_text())['per_session_sha256'].items():
  key=tuple(filename[:-5].split('-',1));assert key not in tape_index;tape_index[key]=(source/'sessions'/filename,expected_hash)
def tape(code,day):
 key=(code,day)
 if key in tape_cache:return tape_cache[key]
 assert day<=summary['end'];path,expected=tape_index[key];assert sha(path)==expected
 packet=json.loads(path.read_text());assert packet['instrument']==code and packet['requested_day']==day
 record=packet.get('methods',{}).get('minutes.history',packet);assert record['status']=='RESPONSE_CAPTURED'
 points=record['response']['points'];assert len(points)==240;windows=[]
 for n in range(0,240,5):
  block=points[n:n+5];end=datetime.fromisoformat(block[-1]['time']);start=end-timedelta(minutes=5)
  prices=[D(p['price_milli'])/1000 for p in block if p['volume']>0]
  evidence={'security_id':code,'day':day,'points':[{'time':p['time'],'volume':p['volume'],'price_milli':p['price_milli']} for p in block]}
  windows.append({'start':start,'end':end,'volume':sum(max(0,p['volume']*100-100) for p in block),
    'buy':max(prices) if prices else None,'sell':min(prices) if prices else None,'evidence':digest(evidence)})
 tape_cache[key]=windows;return windows
def fee_for(gross,action,extra):return cents(max(D(5),gross*D('.0005' if action=='BUY' else '.0015')))+cents(gross*D(extra)/10000)
def audit_children(day,orders,parents,fills,p,extra,cash):
 pmap={r['order_id']:r for r in parents};groups=defaultdict(list)
 for child in orders:
  at=datetime.fromisoformat(child['submitted_at'])
  if at.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()==day:groups[at].append(child)
 fmap={r['order_id']:r for r in fills};assert len(fmap)==len(fills)
 seen=set()
 filled_by_parent=defaultdict(int)
 for at,children in sorted(groups.items()):
  assert len({c['security_id'] for c in children})==len(children),'duplicate security/window child'
  assert len({c['parent_id'] for c in children})==len(children),'duplicate parent/window child'
  reserved=D(0)
  for child in children:
   code=child['security_id'];parent=pmap[child['parent_id']];q=child['quantity'];end=datetime.fromisoformat(child['expires_at'])
   series=tape(code,day);indices=[i for i,w in enumerate(series) if w['start']==at and w['end']==end]
   assert len(indices)==1 and 1<=indices[0]<=46
   i=indices[0];prev,current=series[i-1],series[i];limit=D(child['limit_price']);buy=child['action']=='BUY'
   assert child['security_id']==parent['security_id'] and child['action']==parent['action']
   assert datetime.fromisoformat(parent['submitted_at'])<at and datetime.fromisoformat(parent['expires_at'])>=end
   assert datetime.fromisoformat(child['source_volume_as_of'])==prev['end']
   assert child['source_evidence_id']==prev['evidence'] and child['source_volume_lower_shares']==prev['volume']
   remaining=parent['quantity']-filled_by_parent[parent['order_id']]
   assert 0<q<=min(1000000,prev['volume']*p//10000,remaining)
   assert at.astimezone(ZoneInfo('Asia/Shanghai')).date()==datetime.fromisoformat(parent['eligible_at']).astimezone(ZoneInfo('Asia/Shanghai')).date()
   assert q%100==0 or not buy and q==remaining
   assert not buy or q%100==0
   source=bars[code][day];expected=(D(source['preclose'])*D('1.095' if buy else '.905')).quantize(D('.01'),rounding=ROUND_DOWN if buy else ROUND_UP)
   assert limit==expected
   reserve=limit*q+fee_for(limit*q,child['action'],extra) if buy else D(0)
   assert reserve==D(child['reserved_cash']);reserved+=reserve
   assert child['order_id']==digest({'parent':parent['order_id'],'start':at.isoformat(),'end':end.isoformat(),'quantity':q,'previous_volume':prev['volume'],'evidence_id':prev['evidence']})
   fill=fmap.get(child['order_id'])
   if fill is None:
    assert child['filled_quantity']==0 and child['status'].startswith('UNFILLED_');continue
   seen.add(child['order_id']);fq=fill['quantity'];price=D(fill['price'])
   assert fill['parent_id']==parent['order_id'] and fill['security_id']==code and fill['action']==child['action']
   assert 0<fq<=min(q,current['volume']*p//10000) and child['filled_quantity']==fq
   assert fq%100==0 or not buy and fq==remaining,'illegal odd-share partial fill'
   assert child['status']==('FILLED' if fq==q else 'PARTIAL_WINDOW_EXPIRED')
   assert datetime.fromisoformat(fill['execution_at'])==end
   assert fill['current_evidence_id']==current['evidence'] and fill['current_volume_lower_shares']==current['volume']
   assert price==current['buy' if buy else 'sell'] and (price<limit if buy else price>limit)
   assert not buy or price*fq+fee_for(price*fq,'BUY',extra)<=reserve
  assert reserved<=cash,(day,at,'same-window cash reuse')
  ordered_fills=[fmap[c['order_id']] for c in sorted(children,key=lambda x:(x['action']!='BUY',x['security_id'])) if c['order_id'] in fmap]
  for f in ordered_fills:
   filled_by_parent[f['parent_id']]+=f['quantity']
   assert filled_by_parent[f['parent_id']]<=pmap[f['parent_id']]['quantity']
   gross=D(f['price'])*f['quantity'];cost=fee_for(gross,f['action'],extra)
   cash+=(-gross-cost) if f['action']=='BUY' else gross-cost
   assert cash>=0 and cash==D(f['cash_after'])
 assert seen==set(fmap)
def authenticate_parents(parents,intents):
 expected={}
 for intent in intents:
  for decision in intent['decisions']:
   if decision['action'] not in ('BUY','SELL'):continue
   key=digest({'decision':decision,'snapshot':intent['snapshot_sha256']})
   assert key not in expected
   expected[key]=(intent,decision)
 assert len({p['order_id'] for p in parents})==len(parents)
 assert len({p['decision_id'] for p in parents})==len(parents)
 assert {p['decision_id'] for p in parents}==set(expected)
 for parent in parents:
  intent,decision=expected[parent['decision_id']]
  assert all(parent[k]==decision[k] for k in ('action','security_id','quantity'))
  assert parent['submitted_at']==intent['as_of']
  eligible=datetime.fromisoformat(parent['eligible_at']).astimezone(ZoneInfo('Asia/Shanghai'))
  expiry=datetime.fromisoformat(parent['expires_at']).astimezone(ZoneInfo('Asia/Shanghai'))
  assert eligible.date().isoformat()==intent['execution_session'] and eligible.strftime('%H:%M:%S')=='09:30:00'
  assert expiry.date()==eligible.date() and expiry.strftime('%H:%M:%S')=='14:55:00'
  assert type(parent['quantity']) is int and parent['quantity']>0
  assert type(parent['remaining']) is int and parent['remaining']>=0
  assert type(parent['filled_quantity']) is int and parent['filled_quantity']>=0
  assert parent['remaining']+parent['filled_quantity']==parent['quantity']
assert summary['phase']=='dev' and summary['end']=='2025-12-31'
assert sha(Path(args.plan))==summary['plan_sha256']
assert sha(DATA/'manifest.json')==PLAN['raw_manifest_sha256']
assert sha(PROOF_DIR/'reviewed-manifest.json')==PLAN['proof_manifest_sha256']
assert sha(PROOF_DIR/'capture-manifest.json')==PROOFS['capture_manifest_sha256']
for doc in PROOFS['documents']:
 assert Path(doc['file']).name==doc['file'] and sha(PROOF_DIR/doc['file'])==doc['sha256'] and doc['day']<='2025-12-31'
for code,expected in json.loads((DATA/'manifest.json').read_text())['per_code_sha256'].items():
 assert sha(DATA/'codes'/(code+'.json'))==expected
source_origins={}
for supplement in PROOFS['supplementary_distributions']:
 code=supplement['instrument'];row=supplement['record']
 doc=next(d for d in PROOFS['documents'] if d['file']==supplement['source_file'])
 assert doc['sha256']==supplement['source_sha256'] and doc['instrument']==code and doc['day']==row['dividPlanDate']
 assert row['code']==code[:2].lower()+'.'+code[2:]
 assert all(r['dividOperateDate']!=row['dividOperateDate'] for r in packets[code]['distributions'])
 packets[code]['distributions'].append(dict(row))
 source_origins[(code,row['dividOperateDate'])]=supplement['source_sha256']
events={};event_dates=set()
for code,p in packets.items():
 for r in p['distributions']:
  pair=(code,r['dividOperateDate']);assert pair not in event_dates;event_dates.add(pair)
  assert r['code']==code[:2].lower()+'.'+code[2:]
  cash=D(r['dividCashPsBeforeTax']);stock=D(r['dividStocksPs']);capital=D(r['dividReserveToStockPs'] or '0')
  assert min(cash,stock,capital)>=0
  proofkey=code+'|'+r['dividOperateDate'];tax=PROOFS['stock_dividend_tax_bases'].get(proofkey)
  exemption=PROOFS['capital_tax'].get(proofkey);primary=[];stock_income=D(0)
  if pair in source_origins:primary.append(source_origins[pair])
  for proof in (tax,exemption):
   if proof is None:continue
   doc=next(d for d in PROOFS['documents'] if d['file']==proof['source_file'])
   assert doc['sha256']==proof['source_sha256'] and doc['instrument']==code and doc['day']==r['dividPlanDate']
   primary.append(doc['sha256'])
  if tax:
   assert tax['verified'] is True and stock==D(tax['expected_stock_per_original_share'])>0
   stock_income=D(tax['taxable_income_per_original_share']);assert stock_income>0
  if exemption:assert exemption['verified_exempt'] is True and capital>0
  if not r['dividReserveToStockPs']:
   display=r['dividCashStock']
   assert '转' not in display and (stock==0 and cash>0 and display.startswith('10派') and '送' not in display and not r['dividStockMarketDate']
       or stock>0 and tax and display.startswith('10送'))
  identity={'instrument':code,'source_kind':'PRIMARY_NOTICE_SUPPLEMENT' if pair in source_origins else 'VENDOR_DISTRIBUTION',
   'source_distribution':r,'primary_source_sha256':sorted(set(primary)),
   'effective_stock_taxable_income_per_original_share':str(stock_income),
   'capital_tax_exempt_verified':exemption is not None,'stock_tax_basis_verified':tax is not None}
  key=digest(identity)
  events[key]={'code':code,'record':r['dividRegistDate'],'ex':r['dividOperateDate'],
   'pay':r['dividPayDate'],'list':r['dividStockMarketDate'],'cash':cash,'capital':capital,'stock':stock,
   'stock_income':stock_income,'capital_verified':exemption is not None,'stock_verified':tax is not None}
TARGET=BASE/'illiquidity-development-targets-20261020.json'
assert sha(TARGET)==PLAN['target_sha256']
assert sha(DATA/'calendar.json')==json.loads((DATA/'manifest.json').read_text())['calendar_sha256']
assert set(summary['results_by_profile'])=={f'{p}/{e}/{c}' for p in (100,500,1000) for e in (0,5,10,20,40) for c in ('100000','1000000','10000000','100000000')}
targets=json.loads(TARGET.read_text());first={}
for day,target in sorted(targets.items()):
 assert '2024-01-02'<=day<='2025-12-31' and target['as_of']<day
 for code in target['weights']:first.setdefault(code,day)
assert sha(ROOT/'derived_events.json')==summary['derived_events_sha256']
assert sha(ROOT/'event_source_receipts.json')==summary['event_source_receipts_sha256']
derived=json.loads((ROOT/'derived_events.json').read_text());receipts=json.loads((ROOT/'event_source_receipts.json').read_text())
assert len(derived)==len(events)==len(receipts)==302 and {e['event_id'] for e in derived}==set(events)
expected_zero={k for k,e in events.items() if e['capital']>0 and not e['capital_verified'] or e['stock']>0 and not e['stock_verified']}
assert {r['event_id'] for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']}==expected_zero
for item in derived:
 e=events[item['event_id']]
 assert item['instrument']==e['code'] and item['recorded']==e['record'] and item['ex_date']==e['ex']
 assert (D(item['cash_per_share']),D(item['capital_per_share']),D(item['stock_per_share']),D(item['stock_taxable_income_per_share']))==(e['cash'],e['capital'],e['stock'],e['stock_income'])
 assert item['capital_tax_exempt_verified']==e['capital_verified'] and item['stock_tax_basis_verified']==e['stock_verified']
 assert '2023-12-29'<=e['ex']<='2025-12-31'
def authenticate_failed_case(folder,stated):
 assert stated['status']=='INVALID_SOURCE_OR_ACCOUNT'
 failed=stated['failure_artifact_sha256'];assert 'error.json' in failed
 for name,expected in failed.items():
  assert Path(name).name==name and sha(folder/name)==expected,(name,'failed case artifact changed')
 error=json.loads((folder/'error.json').read_text())
 assert error['status']==stated['status'] and error['error']==stated['error']
 assert 'failed_account_state.json' in failed, 'account factory must construct before a caught replay error'

results={}
for case_id,stated in summary['results_by_profile'].items():
 participation,extra_bps,capital=case_id.split('/');participation=int(participation);extra_bps=int(extra_bps)
 folder=ROOT/case_id
 if stated['status']!='NESTED_EXECUTION_ACCOUNT_RECONCILED':
  authenticate_failed_case(folder,stated)
  results[case_id]={'status':'INVALID_CASE_PRESERVED','reason':stated['error']};continue
 for name,expected in stated['artifact_sha256'].items():assert sha(folder/name)==expected,(capital,name,'changed bytes')
 rows=list(csv.DictReader((folder/'daily.csv').open()))
 assert [r['day'] for r in rows]==sessions
 intents=json.loads((folder/'intents.json').read_text());orders=json.loads((folder/'orders.json').read_text())
 assert all(type(o['quantity']) is int and 0<o['quantity']<=1000000 for o in orders)
 parents=json.loads((folder/'parent_instructions.json').read_text());authenticate_parents(parents,intents)
 by_intent={datetime.fromisoformat(i['as_of']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat():i for i in intents}
 assert len(by_intent)==len(intents)==(24 if summary['phase']=='dev' else 34)
 fills=json.loads((folder/'fills.json').read_text());ledger=json.loads((folder/'corporate_ledger.json').read_text());ownership=json.loads((folder/'ownership.json').read_text())
 by_fill=defaultdict(list);by_ledger=defaultdict(list)
 for f in fills:by_fill[datetime.fromisoformat(f['execution_at']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()].append(f)
 for item in ledger:by_ledger[item['day']].append(item)
 cash=D(capital);lots=defaultdict(list);marks={};claims={};stockclaims={};registered={};nav={};ex_seen=set();record_seen=set();max_capacity=D(0)
 exposure_sum=D(0);exposure_days=0;total_fees=D(0);total_extra_cost=D(0);total_gross_dividend=D(0);total_reserve=D(0);by_year_turnover=defaultdict(lambda:D(0));by_year_fees=defaultdict(lambda:D(0))
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
   key=item['event_id'];e=events[key];q=registered.get(key,0);gross=cents(e['cash']*q);stock_income=cents(e['stock_income']*q);reserve=cents((gross+stock_income)*D('.2'));bonus=e['capital']*q;stock_bonus=e['stock']*q
   assert bonus==int(bonus) and stock_bonus==int(stock_bonus) and item['registered_quantity']==q
   assert reserve<=gross
   if key in expected_zero:assert q==0
   assert D(item['cash_gross'])==gross and D(item['stress_tax_reserve'])==reserve and item['capital_shares']==int(bonus)
   assert item['stock_shares']==int(stock_bonus) and D(item['taxable_stock_income'])==stock_income
   if gross:claims[key]=(next((x for x in sessions if x>e['pay']),None),gross-reserve)
   if bonus+stock_bonus:stockclaims[key]=(e['code'],int(bonus+stock_bonus),e['list'],e['record'])
   total_gross_dividend+=gross;total_reserve+=reserve;ex_seen.add(key)
  expected_stock={key for key,(_,_,at,_) in stockclaims.items() if at<=day}
  actual_stock=[x for x in entries if x['kind'] in ('CAPITAL_SHARES_LISTED','STOCK_DIVIDEND_SHARES_LISTED')]
  assert {x['event_id'] for x in actual_stock}==expected_stock and len(actual_stock)==len(expected_stock)
  for item in actual_stock:
   code,q,at,record=stockclaims.pop(item['event_id']);assert item['quantity']==q
   e=events[item['event_id']];assert not (e['capital'] and e['stock']), 'mixed share kinds need separate independent claims'
   assert item['kind']==('STOCK_DIVIDEND_SHARES_LISTED' if e['stock'] else 'CAPITAL_SHARES_LISTED')
   lots[code].append([q,record])
  audit_children(day,orders,parents,by_fill[day],participation,extra_bps,cash)
  for f in by_fill[day]:
   code=f['security_id'];q=f['quantity'];price=D(f['price']);source=bars[code][day]
   assert type(q) is int and q>0 and source['tradestatus']=='1' and source['isST']=='0'
   assert price==cents(price)
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
  owned_for_record=dict(quantities)
  for code,q,_,_ in stockclaims.values():owned_for_record[code]=owned_for_record.get(code,0)+q
  assert quantities==ownership[day], 'published ownership records listed broker inventory'
  for code,boundary in PROOFS['lifecycles'].items():
   outside=(boundary['kind']=='LISTING_BEGIN' and day<boundary['effective_date'] or boundary['kind']=='DELISTING_END' and day>=boundary['effective_date'])
   if outside:
    assert owned_for_record.get(code,0)==0
    assert not any(p['security_id']==code and p['eligible_at'][:10]<=day<=p['expires_at'][:10] for p in parents)
    if day in by_intent:assert code not in targets[by_intent[day]['execution_session']]['weights']
  actual_record=[x for x in entries if x['kind']=='RECORD_DATE_OWNERSHIP']
  expected_record={key for key,e in events.items() if e['record']==day}
  assert {x['event_id'] for x in actual_record}==expected_record and len(actual_record)==len(expected_record)
  for item in actual_record:
   e=events[item['event_id']];assert not any(c==e['code'] for c,_,_,_ in stockclaims.values())
   q=quantities.get(e['code'],0);assert item['quantity']==q
   registered[item['event_id']]=q;record_seen.add(item['event_id'])
  for code,byday in bars.items():
   boundary=PROOFS['lifecycles'].get(code,{})
   outside=(boundary.get('kind')=='LISTING_BEGIN' and day<boundary['effective_date'] or boundary.get('kind')=='DELISTING_END' and day>=boundary['effective_date'])
   if outside:
    marks.pop(code,None);continue
   source=byday[day];assert source['date']==day and source['tradestatus'] in ('0','1')
   if source['tradestatus']=='1':marks[code]=D(source['close'])
   elif any(e['code']==code and e['ex']==day for e in events.values()):marks[code]=D(source['preclose'])
   elif code not in marks and source['close'] and D(source['close'])>0:marks[code]=D(source['close'])
  market=sum((q*marks[code] for code,q in quantities.items()),D(0))
  pending=sum((q*marks[code] for code,q,_,_ in stockclaims.values()),D(0))
  receivable=sum((net for _,net in claims.values()),D(0));equity=cash+market+pending+receivable
  assert (cash,market,pending,receivable,equity,day_fee,paid)==tuple(D(row[k]) for k in ('cash','market_value','pending_stock_value','cash_receivable','equity','fees','net_dividend_cash_available')),(capital,day,'daily mismatch')
  if day>='2024-01-02':exposure_sum+=(market+pending)/equity;exposure_days+=1
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
 average_exposure=float(exposure_sum/exposure_days*100)
 assert abs(average_exposure-stated['average_exposure_pct'])<1e-10
 r24=(nav['2024-12-31']/D(capital)-1)*100;r25=(nav['2025-12-31']/nav['2024-12-31']-1)*100
 assert abs(float(r24)-stated['2024_return_pct'])<1e-10 and abs(float(r25)-stated['2025_return_pct'])<1e-10
 per_parent=defaultdict(int)
 for fill in fills:per_parent[fill['parent_id']]+=fill['quantity']
 assert len({o['order_id'] for o in orders})==len(orders) and len({f['order_id'] for f in fills})==len(fills)
 for parent in parents:
  assert parent['filled_quantity']==per_parent[parent['order_id']]
  assert parent['remaining']+parent['filled_quantity']==parent['quantity']
  assert parent['status'] in ('FILLED','PARTIAL_DAY_EXPIRED','UNFILLED_DAY_EXPIRED','UNFILLED_HALTED_DAY')
 value={'status':'INDEPENDENT_INTRADAY_LEDGER_RECONSTRUCTED','sessions':len(rows),'children':len(orders),'fills':len(fills),
  'parent_instructions':len(parents),'2024_pct':float(r24),'2025_pct':float(r25),
  'ending_equity_CNY':str(nav[sessions[-1]]),'total_fees_CNY':str(total_fees),
  'all_monthly_feedback_intents_independently_resized':True,'source_window_capacity_prices_evidence_verified':True,
  'per_child_fee_and_window_start_cash_reserve_verified':True,'all_cash_inventory_and_corporate_actions_reconstructed':True}
 value.update({'average_exposure_pct':average_exposure,'zero_entitlements_verified':True,'actual_delisting_exit_verified':True})
 results[case_id]=value
result={'status':'INDEPENDENT_ILLIQUIDITY_DEVELOPMENT_LEDGER_AUDIT_COMPLETE','phase':summary['phase'],'audit_script_sha256':sha(Path(__file__)),
 'replay_summary_sha256':sha(ROOT/'summary.json'),'imports_project_account_code':False,'results_by_profile':results,
 'valid_profiles':sum(r['status']=='INDEPENDENT_INTRADAY_LEDGER_RECONSTRUCTED' for r in results.values()),
 'reconstructed_source_tapes':len(tape_cache),'scope':'Independent Decimal account, source corporate events, prior-close parent sizing, minute-derived sampled prices, previous/current participation caps, per-child fees and window-start reserves; no project account imports.',
 'queue_and_impact_calibrated':False,'historical_arrival_verified':False,'complete_requested_October':False,'objective_achieved':False}
assert len(results)==60
reference=[results.get(f'{p}/40/1000000',{}) for p in (100,500,1000)]
passed=all(r.get('status')=='INDEPENDENT_INTRADAY_LEDGER_RECONSTRUCTED' and min(r.get('2024_pct',0),r.get('2025_pct',0))>0 and r.get('average_exposure_pct',0)>=90 and r.get('zero_entitlements_verified') is True and r.get('actual_delisting_exit_verified') is True for r in reference)
assert passed==summary['raw_development_confirmation_passes']
result.update({'raw_confirmation_passes_independently':passed,'primary_supplement_count':len(PROOFS['supplementary_distributions']),'verified_zero_share_events':len(expected_zero),'2026_strategy_returns_queried':False})
output=Path(args.output);assert not output.exists();output.write_text(json.dumps(result,indent=2)+'\n');print('audit',summary['phase'],'valid profiles',result['valid_profiles'])
