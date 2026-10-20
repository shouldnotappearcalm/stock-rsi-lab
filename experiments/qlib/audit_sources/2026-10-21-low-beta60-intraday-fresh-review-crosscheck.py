import json,csv,hashlib
from pathlib import Path
from decimal import Decimal as D,ROUND_HALF_UP,ROUND_DOWN,ROUND_UP
from datetime import datetime,timedelta,timezone
from collections import defaultdict,Counter
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015');O=B/'low-beta60-intraday-development-20261021'
J=lambda p:json.loads(p.read_text())
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
C=lambda o:hashlib.sha256(json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
cent=lambda x:x.quantize(D('.01'),rounding=ROUND_HALF_UP)
P=J(R/'experiments/qlib/low-beta60-intraday-development-plan.json');S=J(O/'summary.json');assert H(R/'experiments/qlib/low-beta60-intraday-development-plan.json')==S['plan_sha256']
count=0
for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
 for n,h in P[field].items():assert H(root/n)==h,(field,n);count+=1
raw=B/'low-beta60-raw-dev-20261021';rm=J(raw/'manifest.json');bars={}
for c,h in rm['per_code_sha256'].items():
 assert H(raw/'codes'/f'{c}.json')==h
 bars[c]={r['date']:r for r in J(raw/'codes'/f'{c}.json')['bars']}
cal=J(raw/'calendar.json')['sessions'];targets=J(B/'low-beta60-pre2026-formations-20261021/targets.json')['low_beta60']
ev=J(B/'low-beta60-account-source-events-20261021/derived_events.json');assert ev==J(O/'derived_events.json')
assert H(O/'derived_events.json')==S['derived_events_sha256'] and H(O/'event_source_receipts.json')==S['event_source_receipts_sha256']
cap=B/'low-beta60-minutes-dev-20261021';cm=J(cap/'manifest.json');tapes={}
for n,h in cm['per_session_sha256'].items():
 assert H(cap/'sessions'/n)==h
 packet=J(cap/'sessions'/n);code,day=n[:-5].split('-',1);assert packet['instrument']==code and packet['requested_day']==day
 p=packet.get('methods',{}).get('minutes.history',packet)['response']['points'];assert len(p)==240
 windows=[]
 for i in range(0,240,5):
  block=p[i:i+5];prices=[D(v['price_milli'])/1000 for v in block if v['volume']>0];end=datetime.fromisoformat(block[-1]['time']).astimezone(timezone.utc)
  e={'security_id':code,'day':day,'points':[{k:v[k] for k in ('time','volume','price_milli')} for v in block]}
  windows.append({'start':(end-timedelta(minutes=5)).isoformat(),'end':end.isoformat(),'vol':sum(max(0,v['volume']*100-100) for v in block),'buy':max(prices) if prices else None,'sell':min(prices) if prices else None,'id':C(e)})
 tapes[code,day]=windows
assert len(tapes)==1332
results={}
for label,res in S['results_by_profile'].items():
 participation,extra=map(int,label.split('/'));folder=O/label
 assert set(res['artifact_sha256'])=={'daily.csv','intents.json','parent_instructions.json','orders.json','fills.json','corporate_ledger.json','ownership.json'}
 for n,h in res['artifact_sha256'].items():assert H(folder/n)==h
 daily=list(csv.DictReader((folder/'daily.csv').open()));assert [r['day'] for r in daily]==cal
 ints=J(folder/'intents.json');parents=J(folder/'parent_instructions.json');children=J(folder/'orders.json');fills=J(folder/'fills.json');corp=J(folder/'corporate_ledger.json');ownership=J(folder/'ownership.json')
 parents_day=defaultdict(list);children_window=defaultdict(list);fills_window=defaultdict(list)
 for p in parents:parents_day[p['eligible_at'][:10]].append(p)
 for c in children:children_window[c['submitted_at']].append(c)
 for f in fills:fills_window[f['execution_at']].append(f)
 assert len({p['order_id'] for p in parents})==len(parents) and len({c['order_id'] for c in children})==len(children)
 assert len({f['order_id'] for f in fills})==len(fills)
 holdings=defaultdict(list);cash=D(1000000);claims=[];pending=[];ent={};marks={};corp_expected=[];annual={};previous_equity=D(1000000);counter=Counter();saw_children=0;saw_fills=0
 def fee(gross,action):return max(D(5),cent(gross*D(5 if action=='BUY' else 15)/10000))+cent(gross*extra/10000)
 for day,dr in zip(cal,daily):
  div=D(0);dayfees=D(0)
  for cl in claims:
   if not cl['paid'] and cl['available']==day:
    cash+=cl['net'];div+=cl['net'];cl['paid']=True;corp_expected.append({'day':day,'kind':'NET_DIVIDEND_CASH_AVAILABLE','event_id':cl['id'],'cash_delta':str(cl['net'])})
  for e in ev:
   if e['ex_date']!=day:continue
   q=ent.get(e['event_id'],0);gross=cent(q*D(e['cash_per_share']));income=cent(q*D(e['stock_taxable_income_per_share']));tax=cent((gross+income)*D('.2'));capq=q*D(e['capital_per_share']);stockq=q*D(e['stock_per_share']);assert capq==int(capq) and stockq==int(stockq) and tax<=gross
   if gross:claims.append({'id':e['event_id'],'net':gross-tax,'available':next((d for d in cal if d>e['pay_date']),None),'paid':False})
   for qx,kind in [(int(capq),'CAPITAL_SHARES_LISTED'),(int(stockq),'STOCK_DIVIDEND_SHARES_LISTED')]:
    if qx:pending.append({'id':e['event_id'],'code':e['instrument'],'q':qx,'listed':e['listed'],'recorded':e['recorded'],'credited':False,'kind':kind})
   corp_expected.append({'day':day,'kind':'EX_DATE_ENTITLEMENT','event_id':e['event_id'],'instrument':e['instrument'],'registered_quantity':q,'cash_gross':str(gross),'stress_tax_reserve':str(tax),'capital_shares':int(capq),'stock_shares':int(stockq),'taxable_stock_income':str(income)})
  for cl in pending:
   if not cl['credited'] and cl['listed']<=day:
    holdings[cl['code']].append([cl['q'],cl['recorded']]);cl['credited']=True;corp_expected.append({'day':day,'kind':cl['kind'],'event_id':cl['id'],'quantity':cl['q']})
  ps=parents_day[day];remaining={p['order_id']:p['quantity'] for p in ps};filled=Counter()
  for idx in range(1,47):
   expected=[];budget=cash
   for p in sorted(ps,key=lambda p:(p['action']!='SELL',p['security_id'])):
    c=p['security_id'];a=p['action'];left=remaining[p['order_id']]
    if not left or bars[c][day]['tradestatus']=='0':continue
    prev,cur=tapes[c,day][idx-1:idx+1];capacity=prev['vol']*participation//10000
    if a=='SELL':capacity=min(capacity,sum(q for q,bought in holdings[c] if bought<day))
    q=min(left,capacity,1000000);q=q if a=='SELL' and q==left else q//100*100
    limit=(D(bars[c][day]['preclose'])*D('1.095' if a=='BUY' else '.905')).quantize(D('.01'),rounding=ROUND_DOWN if a=='BUY' else ROUND_UP)
    if a=='BUY':
     q=min(q,int(budget/limit)//100*100)
     while q and limit*q+fee(limit*q,a)>budget:q-=100
    if not q:continue
    reserve=limit*q+fee(limit*q,a) if a=='BUY' else D(0);budget-=reserve
    expected.append((p,prev,cur,q,limit,reserve))
   if not expected:continue
   start=expected[0][2]['start'];end=expected[0][2]['end'];obs=children_window[start];assert len(obs)==len(expected),(label,day,start,'child omission')
   for child,(p,prev,cur,q,limit,reserve) in zip(obs,expected):
    assert child['parent_id']==p['order_id'] and child['quantity']==q and D(child['reserved_cash'])==reserve
    assert child['security_id']==p['security_id'] and child['action']==p['action'] and child['submitted_at']==start and child['expires_at']==end
    assert child['source_volume_as_of']==prev['end'] and child['source_volume_lower_shares']==prev['vol'] and child['source_evidence_id']==prev['id'] and D(child['limit_price'])==limit
    assert child['order_id']==C({'parent':p['order_id'],'start':start,'end':end,'quantity':q,'previous_volume':prev['vol'],'evidence_id':prev['id']})
   actualfills=fills_window[end];wantedfills=[]
   for child,(p,prev,cur,q,limit,reserve) in sorted(zip(obs,expected),key=lambda x:(x[0]['action']!='BUY',x[0]['security_id'])):
    a=child['action'];c=child['security_id'];left=remaining[p['order_id']];capacity=cur['vol']*participation//10000;execq=min(left,q,capacity,1000000);execq=execq if a=='SELL' and execq==min(left,q) else execq//100*100
    price=cur['buy' if a=='BUY' else 'sell']
    if not execq or price is None or (price>=limit if a=='BUY' else price<=limit):assert child['status']=='UNFILLED_VOLUME_OR_PRICE' and child['filled_quantity']==0;continue
    gross=price*execq;cost=fee(gross,a)
    if a=='SELL' and cash+gross<cost:assert child['status']=='UNFILLED_FEES_CASH';continue
    if a=='BUY':cash-=gross+cost;holdings[c].append([execq,day])
    else:
     cash+=gross-cost;assert execq<=sum(q0 for q0,bought in holdings[c] if bought<day);leftq=execq
     for lot in holdings[c]:
      if lot[1]<day:take=min(leftq,lot[0]);lot[0]-=take;leftq-=take
     holdings[c]=[lot for lot in holdings[c] if lot[0]]
    assert cash>=0;dayfees+=cost;remaining[p['order_id']]-=execq;filled[p['order_id']]+=execq
    assert child['filled_quantity']==execq and child['status']==('FILLED' if execq==q else 'PARTIAL_WINDOW_EXPIRED')
    wantedfills.append({'order_id':child['order_id'],'parent_id':p['order_id'],'execution_at':end,'security_id':c,'action':a,'quantity':execq,'price':str(price),'cost':str(cost),'cash_after':str(cash),'current_volume_lower_shares':cur['vol'],'current_evidence_id':cur['id']})
   assert actualfills==wantedfills,(label,day,'fills mismatch')
   saw_children+=len(obs);saw_fills+=len(wantedfills)
  for p in ps:
   assert p['remaining']==remaining[p['order_id']] and p['filled_quantity']==filled[p['order_id']]
   wanted='FILLED' if not p['remaining'] else ('UNFILLED_HALTED_DAY' if bars[p['security_id']][day]['tradestatus']=='0' else 'PARTIAL_DAY_EXPIRED' if p['filled_quantity'] else 'UNFILLED_DAY_EXPIRED')
   assert p['status']==wanted
  actualheld={c:sum(q for q,bought in ls) for c,ls in holdings.items() if ls};assert actualheld==ownership[day]
  for e in ev:
   if e['recorded']==day:
    q=actualheld.get(e['instrument'],0);ent[e['event_id']]=q;corp_expected.append({'day':day,'kind':'RECORD_DATE_OWNERSHIP','event_id':e['event_id'],'instrument':e['instrument'],'quantity':q})
  owned=dict(actualheld)
  for cl in pending:
   if not cl['credited']:owned[cl['code']]=owned.get(cl['code'],0)+cl['q']
  for c in owned:
   bar=bars[c][day]
   if bar['tradestatus']=='1':marks[c]=D(bar['close'])
   elif any(e['ex_date']==day and e['instrument']==c for e in ev):marks[c]=D(bar['preclose'])
   elif c not in marks:marks[c]=D(bar['close'])
  mv=sum((q*marks[c] for c,q in actualheld.items()),D(0));pv=sum((cl['q']*marks[cl['code']] for cl in pending if not cl['credited']),D(0));receivable=sum((cl['net'] for cl in claims if not cl['paid']),D(0));eq=cash+mv+pv+receivable
  for k,v in {'cash':cash,'market_value':mv,'pending_stock_value':pv,'cash_receivable':receivable,'equity':eq,'exposure':(mv+pv)/eq,'net_return':eq/previous_equity-1,'fees':dayfees,'net_dividend_cash_available':div}.items():assert D(dr[k])==v,(label,day,k,D(dr[k]),v)
  previous_equity=eq;annual[day[:4]]=eq
  for intent in [i for i in ints if i['as_of'][:10]==day]:
   assert D(intent['equity_at_decision'])==eq and intent['owned_integer_shares']==owned
   target=targets[intent['execution_session']];assert target['as_of']==day
   wanted=[]
   for c in sorted(set(owned)|set(target['weights'])):
    held=owned.get(c,0);w=D(str(target['weights'].get(c,0)));desired=int(eq*w/D(bars[c][day]['close'])/100)*100 if w else 0
    if desired>held:q=(desired-held)//100*100;a='BUY'
    else:q=held-desired;a='SELL'
    if q:wanted.append((a,c,q))
   wanted.sort(key=lambda t:(t[0]!='SELL',t[1]));assert wanted==[(d['action'],d['security_id'],d['quantity']) for d in intent['decisions']]
   batch=C({'decisions':[C({'decision':d,'snapshot':intent['snapshot_sha256']}) for d in intent['decisions']],'at':intent['as_of'],'participation':participation,'extra':str(D(extra)/10000)})
   ips=parents_day[intent['execution_session']];assert len(ips)==len(wanted)
   for p,d in zip(ips,intent['decisions']):
    did=C({'decision':d,'snapshot':intent['snapshot_sha256']});assert p['decision_id']==did and p['order_id']==C({'batch':batch,'decision':did,'role':'intraday_parent'}) and p['submitted_at']==intent['as_of']
  counter['daily']+=1
 assert corp_expected==corp,(label,'corporate ledger')
 assert saw_children==len(children) and saw_fills==len(fills)
 ret24=(annual['2024']/D(1000000)-1)*100;ret25=(annual['2025']/annual['2024']-1)*100;expo=sum((D(d['exposure']) for d in daily[1:]),D(0))/485*100
 for k,v in [('2024_return_pct',ret24),('2025_return_pct',ret25),('average_exposure_pct',expo)]:assert float(v)==res[k]
 results[label]={'returns':[float(ret24),float(ret25)],'exposure':float(expo),'days':len(daily),'intents':len(ints),'parents':len(parents),'children':saw_children,'fills':saw_fills,'corporate_entries':len(corp)}
print(json.dumps({'frozen_file_bindings':count,'raw_packets':len(bars),'minute_packets':len(tapes),'events':len(ev),'results':results,'limitations':['event economic projection reused after hash/equality check; independent primary PDF extraction is parent auditor scope','snapshot hash semantics not independently reconstructed here; parent quantities and record identity links checked']},indent=2))
