"""Independent stdlib complete/failed regime daily-account audit.
No project imports, replay, network, or2026 reads. Annual arithmetic is gated on
both complete profiles; partial failures never receive aggregate returns.
"""
from pathlib import Path
from decimal import Decimal as D, ROUND_HALF_UP
from collections import defaultdict,Counter
import argparse,copy,csv,hashlib,json,subprocess
from datetime import datetime,timezone,timedelta
from math import isclose
RAW='low-market-residual-vol1m-raw-pre2026-20261021';SOURCE='low-market-residual-vol1m-account-source-events-pre2026-20261021';DEV='low-market-residual-vol1m-budgeted-pre2026-development-20261021';OLD_RUN='low-market-residual-vol1m-raw-development-pre2026-20261021';RUN='low-market-residual-vol1m-regime-raw-development-pre2026-20261021'
SOURCE_AUDIT='experiments/qlib/low-market-residual-vol1m-event-source-independent-audit.json'
UNKNOWN={'SH600580|2025-06-27','SH600763|2024-07-05','SH603290|2024-05-23','SH603688|2024-05-22','SH603927|2024-05-21','SZ000403|2025-06-04'}
def check(v,label):
 if not v:raise AssertionError(label)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def cents(x):return x.quantize(D('.01'),rounding=ROUND_HALF_UP)
def qmap(lots):return {c:sum(l['quantity'] for l in v) for c,v in lots.items() if sum(l['quantity'] for l in v)}
def numeric_lots(lots):return {c:[{'quantity':x['quantity'],'bought_on':x['bought_on'],'price':str(D(x['price']))} for x in v] for c,v in lots.items() if v}
def same_lots(a,b):
 check(set(a)==set(b),'final lot issuers')
 for c in a:
  check(len(a[c])==len(b[c]),'final lot count')
  for x,y in zip(a[c],b[c]):check(x['quantity']==y['quantity'] and x['bought_on']==y['bought_on'] and D(x['price'])==D(y['price']),'lot quantity/date/cost')
def same_claims(a,b):
 check(len(a)==len(b),'claim count')
 for x,y in zip(a,b):
  check(set(x)==set(y),'claim fields')
  for k in x:check(D(x[k])==D(y[k]) if k in ('gross','reserve','net') else x[k]==y[k],'claim economic/status field '+k)

PRIMARY='low-market-residual-vol1m-regime-primary-pre2026-20261021'
EVIDENCE='experiments/qlib/low-market-residual-vol1m-regime-evidence.json'
OLD_AUDIT='experiments/qlib/low-market-residual-vol1m-raw-development-independent-failure-audit.json'
LOCAL=timezone(timedelta(hours=8))
OPEN_FIELDS={'date','code','preclose','tradestatus','isST','adjustflag','open'}
def canon(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(x):return hashlib.sha256(canon(x).encode()).hexdigest()
def clock(day,t):return datetime.fromisoformat(day+'T'+t).replace(tzinfo=LOCAL).astimezone(timezone.utc).isoformat()
def at(x):return datetime.fromisoformat(x.replace('Z','+00:00'))
def bands(reference):
 r=D(reference);check(r>=D('.01') and r==cents(r),'regime reference positive cent tick')
 return max(cents(r*D('1.05')),r+D('.01')),max(D('.01'),min(cents(r*D('.95')),r-D('.01')))
def applicable(code,day,when,evidence):
 states=[s for s in evidence['state_intervals'] if s['instrument']==code and s['effective_from']<=day<=s['effective_through']]
 check(len(states)==1,'unique risk state interval for actual dependency')
 s=states[0];check(s['published_on']<s['effective_from'] and at(s['engineering_available_at'])<=at(when),'risk source genuinely visible by engineering clock')
 check(s['actual_arrival_verified'] is False and s['exchange']=='SSE' and s['board']=='MAINBOARD' and s['risk_status']=='OTHER_RISK_WARNING','supported risk class, no arrival upgrade')
 return s
def scope_on(codes,bars,day,required,lifecycles,evidence,when):
 accepted={};exceptions=[];risk_exceptions=[];expected={}
 for code in sorted(codes):
  row=bars(code).get(day);proof=lifecycles.get(code);reason=None
  if proof and proof['kind']=='LISTING_BEGIN' and day<proof['effective_date']:
   check(row is None,'no bar before listing');reason='BEFORE_PRIMARY_LISTING_BOUNDARY'
  if proof and proof['kind']=='DELISTING_END' and day>=proof['effective_date']:reason='AT_OR_AFTER_PRIMARY_DELISTING_BOUNDARY'
  if reason:
   check(code not in required and proof['verified_primary_boundary'] is True,'no dependency in lifecycle gap')
   exceptions.append({'instrument':code,'session':day,'reason':reason,'original_row_present':row is not None,'primary_document_sha256':proof['primary_document_sha256'],'synthetic_price_created':False});continue
  check(row is not None and row['date']==day and row['isST'] in ('0','1'),'complete lifecycle/raw status source')
  active=[s for s in evidence['state_intervals'] if s['instrument']==code and s['effective_from']<=day<=s['effective_through']]
  if row['isST']=='0':
   check(not active,'ordinary row not inconsistent with effective proof');expected[code]={'kind':'ORDINARY_DAILY_OPEN_PROXY','instrument':code,'source_isST':'0','statutory_band_verified':False};accepted[code]=row
  elif not active or at(active[0]['engineering_available_at'])>at(when):
   check(code not in required,'unproven required risk state rejected')
   risk_exceptions.append({'instrument':code,'session':day,'reason':'UNPROVEN_RISK_WARNING_SOURCE_NOT_REQUIRED','original_row_present':True,'source_isST':'1','required_by_account':False,'synthetic_price_created':False})
  else:
   s=applicable(code,day,when,evidence);accepted[code]=row;expected[code]={'kind':'SSE_MAINBOARD_RISK_WARNING','instrument':code,'source_isST':'1','as_of':when,'state_interval_sha256':digest(s),'evidence':evidence,'historical_arrival_verified':False}
 return accepted,exceptions+risk_exceptions,expected

def phases_and_orders(data,sessions,targets,bars,evidence,lifecycles,records):
 """Independent phase visibility, required-source sets, and opening evidence."""
 phase=data['phase_audit'];regime=data['regime_audit'];n=len(data['days'])
 check(len(phase)==4*n and len(regime)==4*n,'four explicit completed phase/audit records per day')
 orders={o['order_id']:o for o in data['orders']};fills={f['order_id']:f for f in data['fills']};allcodes=sorted(records['all_codes']);scope=[];storders=[]
 for i,row in enumerate(data['days']):
  day=row['day'];r=records['by_day'][day];p=phase[4*i:4*i+4];g=regime[4*i:4*i+4]
  check([x['phase'] for x in p]==['PREOPEN_SOURCE_VALIDATED','OPEN_VALIDATED_BEFORE_ACCOUNT_START','OPEN_EXECUTED','CLOSE_RECORDED'],'phase ordering before account mutation')
  check([x['phase'] for x in g]==['PREOPEN','OPEN_VALIDATION','OPEN','CLOSE'],'source/open/close regime ordering')
  for item,t in zip(p,('09:25:00','09:30:00','09:30:00','15:05:00')):check(item['session']==day and item['as_of']==clock(day,t),'phase/session clock')
  check('execution' not in g[0] and not(set(g[0])&{'open','close','high','low','volume'}),'09:25 no opening or full-day values')
  required=r['preopen_required'];check(p[0]['required']==sorted(required),'PREOPEN only existing physical/order/ex dependencies')
  pre,ex,reg=scope_on(allcodes,bars,day,required,lifecycles,evidence,clock(day,'09:25:00'))
  check(g[0]['regimes']==reg,'every PREOPEN regime source reconstructed');scope.extend(ex)
  nextday=sessions[sessions.index(day)+1] if sessions.index(day)+1<len(sessions) else None
  target=targets.get(nextday);closing=set(r['owned'])|required|set((target or {}).get('weights',{}));check(p[3]['required']==sorted(closing),'new target introduced only at CLOSE')
  close,ex,reg=scope_on(allcodes,bars,day,closing,lifecycles,evidence,clock(day,'15:05:00'))
  for item in ex:
   if item not in scope:scope.append(item)
  check(g[3]['regimes']==reg,'every CLOSE regime source reconstructed')
  due=[o for o in data['orders'] if o['eligible_at']==clock(day,'09:30:00')]
  expectedcodes=sorted({o['security_id'] for o in due})
  for offset,validate in ((1,True),(2,False)):
   details=g[offset]['execution'];check([x['instrument'] for x in details]==expectedcodes,'all opening pending issuers audited exactly')
   for detail in details:
    code=detail['instrument'];src=pre[code];quote={k:v for k,v in src.items() if k in OPEN_FIELDS};risk=src['isST']=='1';upper,lower=bands(src['preclose']) if risk else (D(src['preclose'])*D('1.095'),D(src['preclose'])*D('.905'))
    check(detail['quote']==quote and not(set(detail['quote'])&{'high','low','close','volume','amount'}),'OPEN exact allowed original fields, no future data')
    check(detail['validate_only'] is validate and detail['phase']=='OPEN','opening validation/execution audit identity')
    if src['tradestatus']=='1':check(D(detail['limit_up'])==upper and D(detail['limit_down'])==lower,'explicit actual opening reference limits')
    expectedorders=[o for o in due if o['security_id']==code];check([o['order_id'] for o in detail['orders']]==[o['order_id'] for o in expectedorders],'complete opening order audit')
    for item,o in zip(detail['orders'],expectedorders):
     check(item['quantity']==o['quantity'] and item['action']==o['action'],'opening order unchanged quantity/action')
     if risk:
      applicable(code,day,clock(day,'09:25:00'),evidence);check(o['order_type']==item['order_type']=='LIMIT' and D(o['limit_price'])==D(item['limit_price'])==(upper if o['action']=='BUY' else lower),'ST explicit LIMIT direction preserved')
      if o['action']=='BUY' and evidence['account_capabilities']['risk_warning_buy_permission'] is False:check(o['status']==item['planned_status']=='UNFILLED_RISK_WARNING_PERMISSION' and o['order_id'] not in fills,'unpermitted STBUY terminal rejection')
      storders.append({'session':day,'instrument':code,'order_id':o['order_id'],'action':o['action'],'status':o['status']})
     if not validate:check(item['final_status']==o['status'],'actual opening final order state')
 if data['source_scope_audit']!=scope:
  mismatch=next(((x,y) for x,y in zip(data['source_scope_audit'],scope) if x!=y),None)
  raise AssertionError('source exception mismatch lengths '+str((len(data['source_scope_audit']),len(scope)))+' first '+str(mismatch))
 return {'all_completed_phases_reconstructed':True,'source_scope_rows_reconstructed':len(scope),'actual_ST_orders':list({x['order_id']:x for x in storders}.values()),'ST_limit_orders_exercised_in_actual_account':bool(storders)}

def audit_profile(data,bps,events,sessions,targets,bars,evidence,allcodes,state=None):
 complete_days=[r['day'] for r in data['days']];check(complete_days==sessions[:len(complete_days)],'continuous original-session prefix')
 check([i['execution_session'] for i in data['intents']]==list(targets)[:len(data['intents'])],'frozen monthly intentions in order')
 byevent={e['event_id']:e for e in events};fd=defaultdict(list);cd=defaultdict(list)
 for f in data['fills']:check(f['execution_at'][:10] in complete_days,'only completed-session fills');fd[f['execution_at'][:10]].append(f)
 for c in data['corporate_ledger']:check(c['day'] in complete_days,'only completed-session corporate entries');cd[c['day']].append(c)
 cash=D('1000000');lots={};cashclaims=[];stockclaims=[];entitlements={};daily_owned={};marks={};record_quantities={};fees_total=D(0);signed_total=D(0);cashcredits=D(0)
 previous_equity=D('1000000');records={'all_codes':allcodes,'by_day':{}};held_ST=[]
 for row in data['days']:
  day=row['day'];beforecash=cash;netcash=D(0);dayfee=D(0)
  required=set(qmap(lots))|{x['instrument'] for x in stockclaims if not x['credited']}|{o['security_id'] for o in data['orders'] if o['eligible_at']==clock(day,'09:30:00')}
  required.update(e['instrument'] for e in events if e['ex_date']==day and entitlements.get(e['event_id'],0))
  # start_day credits occur before open fills; record ownership occurs after fills.
  for c in cd[day]:
   kind=c['kind'];eid=c['event_id'];e=byevent[eid];code=e['instrument']
   if kind=='RECORD_DATE_OWNERSHIP':continue
   if kind=='NET_DIVIDEND_CASH_AVAILABLE':
    choices=[x for x in cashclaims if x['event_id']==eid and not x['paid'] and x['available_on']==day];check(len(choices)==1,'one due cash claim');claim=choices[0];check(D(c['cash_delta'])==D(claim['net']),'netcash claim amount');claim['paid']=True;cash+=D(claim['net']);netcash+=D(claim['net']);cashcredits+=D(claim['net'])
   elif kind=='EX_DATE_ENTITLEMENT':
    quantity=entitlements.get(eid,0);check(day==e['ex_date'] and c['registered_quantity']==quantity and type(quantity) is int,'record/ex actual ownership')
    check(not quantity or (D(e['capital_per_share'])==0 or e['capital_tax_exempt_verified']) and (D(e['stock_per_share'])==0 or e['stock_tax_basis_verified']),'unknown tax positive ownership must not pass')
    cap=D(e['capital_per_share'])*quantity;stock=D(e['stock_per_share'])*quantity;check(cap==int(cap) and stock==int(stock),'integer registry quantities before credits')
    gross=cents(D(e['cash_per_share'])*quantity);income=cents(D(e['stock_taxable_income_per_share'])*quantity);reserve=cents((gross+income)*D('.2'))
    check(c['capital_shares']==int(cap) and c['stock_shares']==int(stock) and D(c['cash_gross'])==gross and D(c['taxable_stock_income'])==income and D(c['stress_tax_reserve'])==reserve,'all EX amounts independently reconstructed')
    if gross:
     available=next((d for d in sessions if d>e['pay_date']),None);cashclaims.append({'event_id':eid,'instrument':code,'gross':str(gross),'reserve':str(reserve),'net':str(gross-reserve),'available_on':available,'paid':False})
    for n,sharekind in ((int(cap),'CAPITAL_TRANSFER'),(int(stock),'STOCK_DIVIDEND')):
     if n:stockclaims.append({'event_id':eid,'instrument':code,'quantity':n,'listed':e['listed'],'recorded':e['recorded'],'credited':False,'share_kind':sharekind})
   else:
    check(kind in ('CAPITAL_SHARES_LISTED','STOCK_DIVIDEND_SHARES_LISTED'),'known corporate ledger kind')
    sharekind='CAPITAL_TRANSFER' if kind=='CAPITAL_SHARES_LISTED' else 'STOCK_DIVIDEND';choices=[x for x in stockclaims if x['event_id']==eid and x['share_kind']==sharekind and not x['credited'] and x['listed']<=day];check(len(choices)==1,'one due stock claim');claim=choices[0];check(c['quantity']==claim['quantity'],'listed quantity conserved');claim['credited']=True;lots.setdefault(code,[]).append({'quantity':claim['quantity'],'bought_on':claim['recorded'],'price':'0'})
  for f in fd[day]:
   c=f['security_id'];n=f['quantity'];buy=f['action']=='BUY';check(type(n) is int and n>0 and (not buy or n%100==0),'positive integer/100lot fill')
   src=bars(c)[day];price=D(f['price']);check(src['tradestatus']=='1' and price==D(src['open']),'actual raw opening source')
   reference=D(src['preclose'])
   if src['isST']=='0':upper,lower=reference*D('1.095'),reference*D('.905')
   else:
    applicable(c,day,clock(day,'09:25:00'),evidence);upper,lower=bands(reference);check(lower<=price<=upper,'ST actual opening inside statutory five-percent band')
    check(not buy or evidence['account_capabilities']['risk_warning_buy_permission'] is True,'ST BUY capability before fills')
   check(price<upper if buy else price>lower,'frozen directional conservative limits')
   check(D(src['volume'])>0 and n<=D(src['volume']),'observed daily volume necessary condition')
   gross=price*n;fee=cents(max(D(5),gross*(D('.0005') if buy else D('.0015'))))+cents(gross*D(bps)/10000);check(fee==D(f['cost']),'separately rounded base+extra fees');fees_total+=fee;dayfee+=fee;signed_total+=gross if buy else -gross
   if buy:cash-=gross+fee;lots.setdefault(c,[]).append({'quantity':n,'bought_on':day,'price':str(price)})
   else:
    check(n<=sum(x['quantity'] for x in lots.get(c,[]) if x['bought_on']<day),'T+1 available lots');left=n
    for lot in lots[c]:
     if lot['bought_on']>=day:continue
     removed=min(left,lot['quantity']);lot['quantity']-=removed;left-=removed
    check(left==0,'sell source inventory removal');lots[c]=[x for x in lots[c] if x['quantity']]
    if not lots[c]:del lots[c]
    cash+=gross-fee
   check(cash==D(f['cash_after']) and cash>=0,'each fill cash bridge')
  for c in cd[day]:
   if c['kind']!='RECORD_DATE_OWNERSHIP':continue
   e=byevent[c['event_id']];quantity=qmap(lots).get(e['instrument'],0);check(e['recorded']==day and c['quantity']==quantity,'all record-date quantities independently rebuilt');entitlements[e['event_id']]=quantity;record_quantities[e['event_id']]=quantity
  listed=qmap(lots);check(data['ownership'][day]==listed,'every partial daily listed ownership')
  pending=defaultdict(int)
  for x in stockclaims:
   if not x['credited']:pending[x['instrument']]+=x['quantity']
  owned=dict(listed)
  for c,n in pending.items():owned[c]=owned.get(c,0)+n
  daily_owned[day]=owned
  for c in owned:
   src=bars(c)[day]
   if src['tradestatus']=='1':marks[c]=D(src['close'])
   elif any(e['instrument']==c and e['ex_date']==day for e in events):marks[c]=D(src['preclose'])
   elif c not in marks and src['close'] and D(src['close'])>0:marks[c]=D(src['close'])
   check(c in marks and marks[c]>0,'every owned/pending share visible raw mark')
   if src['isST']=='1':
    applicable(c,day,clock(day,'09:25:00'),evidence);held_ST.append({'session':day,'instrument':c,'owned_shares':owned[c],'raw_close':src['close'],'used_mark':str(marks[c]),'source_isST':'1'})
  market=sum((n*marks[c] for c,n in listed.items()),D(0));pendingvalue=sum((n*marks[c] for c,n in pending.items()),D(0));receivable=sum((D(x['net']) for x in cashclaims if not x['paid']),D(0))
  check(cash==D(row['cash']) and market==D(row['market_value']) and pendingvalue==D(row['pending_stock_value']) and receivable==D(row['cash_receivable']),'every partial daily cash and asset component')
  check(cash+market+pendingvalue+receivable==D(row['equity']),'every partial daily equity conservation')
  check(dayfee==D(row['fees']) and netcash==D(row['net_dividend_cash_available']),'every daily fee/cash credit')
  check(D(row['net_return'])==(D(row['equity'])/previous_equity-1) and D(row['exposure'])==(market+pendingvalue)/D(row['equity']),'daily return/exposure arithmetic')
  previous_equity=D(row['equity']);records['by_day'][day]={'preopen_required':required,'owned':owned}
 check(cash==D('1000000')-signed_total-fees_total+cashcredits,'aggregate continuous cash conservation')
 if state is not None:
  check(cash==D(state['cash']),'failed cash retained');same_lots(lots,state['positions']);same_claims(cashclaims,state['cash_claims']);same_claims(stockclaims,state['stock_claims']);check(entitlements==state['entitlements'],'retained registered entitlements')
  check(daily_owned[complete_days[-1]]==state['owned_shares'],'final failed owned shares incl pending claims')
 unknown=[]
 for e in events:
  key=e['instrument']+'|'+e['ex_date']
  if key not in UNKNOWN:continue
  rr=[r for r in data['corporate_ledger'] if r['event_id']==e['event_id'] and r['kind']=='RECORD_DATE_OWNERSHIP'];xx=[r for r in data['corporate_ledger'] if r['event_id']==e['event_id'] and r['kind']=='EX_DATE_ENTITLEMENT'];check(len(rr)==len(xx)==1 and rr[0]['quantity']==xx[0]['registered_quantity']==0,'six unknown actual zero record and EX ownership')
  unknown.append({'event_key':key,'event_id':e['event_id'],'record_quantity':0,'ex_registered_quantity':0,'tax_verification_granted':False})
 check(len(unknown)==6,'six unknown events retained')
 for e in events:
  for kind,dayfield in (('RECORD_DATE_OWNERSHIP','recorded'),('EX_DATE_ENTITLEMENT','ex_date')):
   if e[dayfield] in complete_days:check(sum(x['event_id']==e['event_id'] and x['kind']==kind for x in cd[e[dayfield]])==1,'every due event record/ex exactly once')
 for intent in data['intents']:
  execution=intent['execution_session'];asof=intent['as_of'][:10];check(asof==sessions[sessions.index(execution)-1]==targets[execution]['as_of'],'priorclose next-session intent')
  check(intent['owned_integer_shares']==daily_owned[asof],'intent actual owned integer inventory');check(D(intent['equity_at_decision'])==D(next(x['equity'] for x in data['days'] if x['day']==asof)),'priorclose account equity')
  receipt=intent['allocation_receipt'];check(receipt['execution_prices_or_returns_used'] is False and receipt['future_cash_or_fill_guaranteed'] is False and receipt['physical_integer_orders'] is True,'budgeted receipt boundaries')
  check(D(str(receipt['final_planned_notional']))<=D(str(receipt['target_notional_budget']))+D('.0001'),'allocation fixed notional budget')
  post=dict(intent['owned_integer_shares'])
  for d in intent['decisions']:
   check(type(d['quantity']) is int and d['quantity']>0 and (d['action']!='BUY' or d['quantity']%100==0),'physical decisions lots');c=d['security_id'];post[c]=post.get(c,0)+d['quantity']*(1 if d['action']=='BUY' else -1)
  for c,n in receipt['post_order_normalized_positions'].items():check(D(str(n))==post.get(c,0),'budgeted receipt matches emitted physical decisions')
 return {'daily_rows_reconstructed':len(complete_days),'monthly_intents_reconstructed':len(data['intents']),'fills_reconstructed':len(data['fills']),'corporate_records_reconstructed':len(data['corporate_ledger']),'cash_reconstructed_CNY':str(cash),'signed_fill_notional_CNY':str(signed_total),'fill_costs_CNY':str(fees_total),'net_cash_credits_CNY':str(cashcredits),'final_integer_listed_lots':numeric_lots(lots),'final_pending_stock_claims':[x for x in stockclaims if not x['credited']],'actual_six_unknown_zero_ownership':unknown,'actual_ST_owned_raw_marks':held_ST},records

def verify_orders(data):
 expected=[]
 for intent in data['intents']:
  for decision in intent['decisions']:
   did=digest({'decision':decision,'snapshot':intent['snapshot_sha256']});expiry=clock(intent['execution_session'],'09:30:00')
   oid=digest({'decision_id':did,'at':intent['as_of'],'expires_at':expiry})
   expected.append({'order_id':oid,'decision_id':did,'security_id':decision['security_id'],'action':decision['action'],'quantity':decision['quantity'],'submitted_at':intent['as_of'],'eligible_at':expiry,'expires_at':expiry})
 check(len(expected)==len(data['orders']),'every physical intent has exactly one order')
 fills={f['order_id']:f for f in data['fills']};check(len(fills)==len(data['fills']),'no repeated daily-proxy fill per order')
 for exp,actual in zip(expected,data['orders']):
  check(all(actual[k]==v for k,v in exp.items()),'exact decision/order hash and priorclose/nextopen link')
  if actual['order_id'] in fills:
   f=fills[actual['order_id']];check(f['action']==actual['action'] and f['security_id']==actual['security_id'] and f['execution_at']==actual['eligible_at'] and f['quantity']<=actual['quantity'],'fill identity/session/requested bound')
   check(actual['status']==('FILLED' if f['quantity']==actual['quantity'] else 'PARTIAL_DAY_EXPIRED'),'final filled status')
  else:check(actual['status'] in ('UNFILLED_MARKET_CONSTRAINT','UNFILLED_CASH_OR_T1','UNFILLED_RISK_WARNING_PERMISSION','UNFILLED_RISK_WARNING_BUY_CAP','PENDING'),'unfilled order retained')
 return {'orders_independently_linked_to_frozen_intents':len(expected),'order_status_counts':dict(sorted(Counter(o['status'] for o in data['orders']).items()))}

def metrics(data):
 rows=data['days'];check(len(rows)==486 and rows[0]['day']=='2023-12-29' and rows[-1]['day']=='2025-12-31','annual arithmetic only after complete source window')
 nav={r['day']:D(r['equity']) for r in rows};initial=D('1000000');peak=initial;dd=D(0);exposures=[]
 for r in rows:
  eq=D(r['equity']);check(eq.is_finite() and eq>0,'finite positive account NAV');peak=max(peak,eq);dd=min(dd,eq/peak-1)
  if r['day']>='2024-01-02':exposures.append(D(r['exposure']))
 check(len(exposures)==485,'fixed exposure sessions')
 return {'2024_return_pct':float((nav['2024-12-31']/initial-1)*100),'2025_return_pct':float((nav['2025-12-31']/nav['2024-12-31']-1)*100),'net_compound_return_pct':float((nav['2025-12-31']/initial-1)*100),'average_exposure_pct':float(sum(exposures,D(0))/485*100),'max_drawdown_pct':float(dd*100),'cost_pct_initial':float(sum((D(r['fees']) for r in rows),D(0))/initial*100),'orders':len(data['orders']),'fills':len(data['fills']),'monthly_decisions':len(data['intents']),'account_sessions':486,'outcome_sessions':485}

def compare_prefix(data,prefix):
 trace,state=prefix['trace'],prefix['state'];cut=trace['failed_session'];check(cut=='2025-12-16' and len(trace['days'])==474,'immutable historical failure boundary')
 for key,new,old in (('daily',data['days'][:474],trace['days']),('intents',data['intents'],trace['intents']),('fills',[x for x in data['fills'] if x['execution_at'][:10]<cut],state['fills']),('corporate',[x for x in data['corporate_ledger'] if x['day']<cut],state['corporate_ledger']),('ownership',{d:q for d,q in data['ownership'].items() if d<cut},trace['ownership'])):check(new==old,'original failed-account literal financial prefix '+key)
 return {'old474_days_identical':True,'all24_intents_identical':True,'pretransition_fills_corporate_ownership_identical':True,'old_failure_unchanged_and_not_relabelled_success':True}

def authenticate_primary(base,repo,known):
 primary=base/PRIMARY;e=read(repo/EVIDENCE);manifest=read(primary/'manifest.json');public=read(repo/'experiments/qlib/low-market-residual-vol1m-regime-primary-source-manifest.json')
 check(manifest==public and manifest['status']=='HASH_VERIFIED_EXISTING_PRIMARY_READING_BYTES_IMPORTED_NO_NEW_NETWORK','exact authenticated primary cache manifest')
 for n,h in manifest['artifact_sha256'].items():check(sha(primary/n)==h==known[str((primary/n).resolve())],'every original primary byte and reading artifact')
 docs={d['file']:d for d in manifest['documents']};check(len(docs)==2,'two fixed original rule/state documents')
 rule=e['rule_document'];states=e['state_intervals'];check(e['contract']=='SSE_MAINBOARD_RISK_WARNING_PRE2026_V1' and e['account_capabilities']=={'risk_warning_buy_permission':False},'fixed contract and no synthetic permission')
 check(rule=={'source_file':'sse-trading-rules-2023.docx','sha256':docs['sse-trading-rules-2023.docx']['sha256'],'published_on':'2023-02-17','valid_from':'2023-12-29','valid_through':'2025-12-31'},'exact reviewed original exchange rule')
 check(states==[{'instrument':'SH600079','exchange':'SSE','board':'MAINBOARD','risk_status':'OTHER_RISK_WARNING','effective_from':'2025-12-16','effective_through':'2025-12-31','published_on':'2025-12-13','engineering_available_at':'2025-12-14T00:00:00+08:00','actual_arrival_verified':False,'source_file':'issuer-www-st-notice.pdf','source_sha256':docs['issuer-www-st-notice.pdf']['sha256']}],'exact issuer state interval and conservative availability boundary')
 receipts=read(primary/'reading-download-receipts-additional.json')
 for d in docs.values():
  rr=[r for r in receipts if Path(r['local_file']).name==d['file']];check(len(rr)==1 and rr[0]['status']==200 and rr[0]['body_sha256']==d['sha256']==sha(primary/d['file']),'actual primary original receipt-byte chain')
 research=read(repo/'experiments/qlib/low-market-residual-vol1m-regime-primary-source-research.json')
 check(manifest['source_research_sha256']==sha(repo/'experiments/qlib/low-market-residual-vol1m-regime-primary-source-research.json') and research['primary_notice']['pdf_sha256']==states[0]['source_sha256'] and research['existing_cash_share_trading']['attachment_sha256']==rule['sha256'],'research review binds actual original bytes')
 check(research['public_time_boundaries']['earliest_primary_public_timestamp_authenticated'] is False,'no historical source arrival certification')
 return e,{'manifest_sha256':sha(primary/'manifest.json'),'rule_sha256':rule['sha256'],'state_notice_sha256':states[0]['source_sha256'],'historical_arrival_verified':False}

def negative_controls(data,bps,events,sessions,targets,bars,evidence,allcodes,records,lifecycles):
 controls={}
 def rejected(label,fn):
  try:fn()
  except (AssertionError,ValueError,KeyError):controls[label]=True
  else:raise AssertionError('semantic negative was accepted: '+label)
 mutated=copy.deepcopy(data);mutated['fills'][0]['cost']=str(D(mutated['fills'][0]['cost'])+D('.01'))
 rejected('independent_fill_fee_plus_one_cent',lambda:audit_profile(mutated,bps,events,sessions,targets,bars,evidence,allcodes))
 mutated=copy.deepcopy(data);mutated['days'][0]['cash']=str(D(mutated['days'][0]['cash'])+D('.01'))
 rejected('daily_cash_component_plus_one_cent',lambda:audit_profile(mutated,bps,events,sessions,targets,bars,evidence,allcodes))
 mutated=copy.deepcopy(data);next(x for x in mutated['corporate_ledger'] if x['kind']=='RECORD_DATE_OWNERSHIP')['quantity']+=1
 rejected('record_date_registered_quantity_changed',lambda:audit_profile(mutated,bps,events,sessions,targets,bars,evidence,allcodes))
 mutated=copy.deepcopy(data);mutated['regime_audit'][0]['execution']=[{'quote':{'open':'1'}}]
 rejected('opening_quote_in_0925_phase',lambda:phases_and_orders(mutated,sessions,targets,bars,evidence,lifecycles,records))
 mutated=copy.deepcopy(data);mutated['phase_audit'][1]['as_of']=clock(sessions[0],'09:25:00')
 rejected('opening_validation_pretends_to_be_preopen',lambda:phases_and_orders(mutated,sessions,targets,bars,evidence,lifecycles,records))
 if any(r['owned'].get('SH600079',0) for d,r in records['by_day'].items() if d>='2025-12-16'):
  late=copy.deepcopy(evidence);late['state_intervals'][0]['engineering_available_at']='2025-12-31T23:59:59+08:00'
  rejected('required_ST_proof_arrives_after_held_date',lambda:audit_profile(data,bps,events,sessions,targets,bars,late,allcodes))
 return controls

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('source-root','repo-root','plan','expected-plan-sha256','freeze-commit','output'):p.add_argument('--'+n,required=True)
 p.add_argument('--terminal-confirmed',action='store_true');a=p.parse_args();check(a.terminal_confirmed,'explicit actual terminal confirmation required before any account read')
 base,repo,out=map(lambda s:Path(s).resolve(),(a.source_root,a.repo_root,a.output));root=base/RUN
 check(not out.exists() and not out.is_relative_to(base) and not out.is_relative_to(repo),'new external audit report path required')
 planpath=Path(a.plan).resolve();check(sha(planpath)==a.expected_plan_sha256,'external frozen regime plan');plan=read(planpath)
 check(plan['status']=='FROZEN_IVOL_REGIME_RAW_PRE2026_DAILY_ENGINEERING_PLAN' and plan['initial_CNY']=='1000000' and plan['extra_cost_bps']==[20,40] and plan['risk_warning_buy_permission'] is False and plan['window']==['2023-12-29','2025-12-31'],'frozen account scope')
 known=read(root/'input-before.json');summary=read(root/'summary.json');post=read(root/'input-postcheck.json')
 check(summary['plan_sha256']==a.expected_plan_sha256 and summary['method_code_sha256']==plan['method_code_sha256'],'actual account plan/method identity')
 for n,h in {**plan['method_code_sha256'],plan['protocol_file']:plan['protocol_sha256']}.items():
  check(sha(repo/n)==h==hashlib.sha256(subprocess.check_output(['git','show',a.freeze_commit+':'+n],cwd=repo)).hexdigest(),'actual method/protocol frozen blob '+n)
 rel=str(planpath.relative_to(repo));check(hashlib.sha256(subprocess.check_output(['git','show',a.freeze_commit+':'+rel],cwd=repo)).hexdigest()==a.expected_plan_sha256,'exact frozen plan commit blob')
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for n,h in plan[field].items():check(sha(parent/n)==h==known[str((parent/n).resolve())],'all exact plan map inputs '+n)
 for n,h in known.items():check(sha(n)==h,'every authenticated before/after actual input')
 check(post=={'source_inputs_unchanged_after_replay':True} and summary['postcheck_sha256']==sha(root/'input-postcheck.json') and summary['source_inputs_unchanged_after_replay'] is True,'post-replay actual all-input verification')
 for f in ('2026_return_computed','new_2026_queries','candidate_promoted','objective_achieved','minute_execution_admitted','actual_FIFO_tax_liability_verified','historical_arrival_verified','historical_arrival_certified','queue_and_impact_calibrated','full_corporate_actions_certified'):check(summary[f] is False,'research/economic certification boundary '+f)
 check(set(summary['results_by_extra_bps'])=={'20','40'} and read(root/'case_results.json')==summary['results_by_extra_bps'],'both fixed cost profiles retained')
 sa=read(repo/SOURCE_AUDIT);check(sa['status']=='PASS_INDEPENDENT_PRE2026_EVENT_SOURCE_AUDIT' and sa['all862_events_independently_reconstructed'] is True and sa['imports_project_code'] is False,'independent event source evidence')
 for n,h in sa['source_artifact_sha256'].items():check(sha(base/SOURCE/n)==h==known[str((base/SOURCE/n).resolve())],'actual independently audited event source '+n)
 check(summary['source_projection_summary_sha256']==sa['source_summary_sha256'],'account consumes independently audited source summary')
 oldaudit=read(repo/OLD_AUDIT);check(oldaudit['status']=='PASS_INDEPENDENT_FAILED_RAW_ACCOUNT_PRESERVATION_AUDIT' and oldaudit['imports_project_code'] is False and oldaudit['annual_scorer_called'] is False,'original failure remains authentic independent evidence')
 for n,h in oldaudit['all_output_file_sha256'].items():check(sha(base/OLD_RUN/n)==h==known[str((base/OLD_RUN/n).resolve())],'all old failure output bytes unchanged')
 check(oldaudit['summary_sha256']==sha(base/OLD_RUN/'summary.json'),'old13/failure summary independent anchor')
 check(len(sa['old42_financial_sha256'])==42,'old42 budgeted financial input scope')
 for n,h in sa['old42_financial_sha256'].items():check(sha(base/DEV/n)==h==known[str((base/DEV/n).resolve())],'old42 actual financial bytes unchanged')
 evidence,primaryproof=authenticate_primary(base,repo,known)
 events=read(base/SOURCE/'derived_events.json');check(len(events)==862,'fixed862 canonical events')
 targets=read(base/DEV/'targets.json')['low_market_residual_vol_1m'];sessions=read(base/RAW/'calendar.json')['sessions'];check(len(sessions)==486 and sessions[0]=='2023-12-29' and sessions[-1]=='2025-12-31' and len(targets)==24,'fixed full pre2026 source/targets window')
 manifest=read(base/RAW/'manifest.json');allcodes=sorted(manifest['per_code_sha256']);check(len(allcodes)==361,'all361 original issuers')
 cache={}
 def bars(c):
  if c not in cache:
   path=base/RAW/'codes'/(c+'.json');check(sha(path)==manifest['per_code_sha256'][c]==known[str(path.resolve())],'original raw packet literal bytes')
   packet=read(path);check(packet['window']==['2023-12-29','2025-12-31'] and all(r['date']<='2025-12-31' for r in packet['bars']),'only capped pre2026 raw observations')
   cache[c]={r['date']:r for r in packet['bars']};check(len(cache[c])==len(packet['bars']),'unique actual source dates')
  return cache[c]
 lifecycles=read(base/SOURCE/'lifecycles.json')['boundaries'];profiles={};data_by_bps={};record_by_bps={};complete=True
 for b in (20,40):
  folder=root/str(b);result=summary['results_by_extra_bps'][str(b)];done=result['status']=='RAW_DAILY_PROXY_RECONCILED';complete=complete and done
  files={x.name:sha(x) for x in folder.iterdir() if x.is_file()};check(files==result['artifact_sha256' if done else 'failure_artifact_sha256'],'all actual complete/failure artifact SHA files')
  if done:
   with (folder/'daily.csv').open(newline='') as stream:days=list(csv.DictReader(stream))
   data={'days':days,**{key:read(folder/(key+'.json')) for key in ('intents','fills','orders','corporate_ledger','ownership','regime_audit','phase_audit','source_scope_audit')}};state=None
   check([r['day'] for r in days]==sessions and len(data['intents'])==24,'complete486days/24intents before aggregate arithmetic')
  else:
   check(result['annual_returns_computed'] is False and not any('return_pct' in k or k in ('average_exposure_pct','max_drawdown_pct') for k in result),'no failed annual/exposure scorer values')
   trace=read(folder/'partial_engine_trace.json');state=read(folder/'failed_account_state.json')
   data={'days':trace['days'],'intents':trace['intents'],'ownership':trace['ownership'],'source_scope_audit':trace['source_scope_audit'],**{k:state[k] for k in ('fills','orders','corporate_ledger')},'regime_audit':trace['regime_audit'][:4*len(trace['days'])],'phase_audit':trace['phase_audit'][:4*len(trace['days'])]}
   check(trace['failed_session'] not in [r['day'] for r in data['days']],'failing session never falsely completed')
  prof,records=audit_profile(data,b,events,sessions,targets,bars,evidence,allcodes,state);profiles[str(b)]=prof;data_by_bps[b]=data;record_by_bps[b]=records
  prof.update(verify_orders(data));prof.update(phases_and_orders(data,sessions,targets,bars,evidence,lifecycles,records))
  if done:
   prefix={'trace':read(base/OLD_RUN/str(b)/'partial_engine_trace.json'),'state':read(base/OLD_RUN/str(b)/'failed_account_state.json')};prof['ordinary_prefix_regression']=compare_prefix(data,prefix)
   check(read(folder/'ordinary_prefix_regression.json')=={'old_partial_days':474,'old_failed_session':'2025-12-16','financial_prefix_byte_semantics_identical':True,'all24_monthly_intents_identical':True,'old_source_guard_failure_relabelled_success':False},'actual prefix regression receipt exact')
 check(summary['annual_returns_computed'] is complete and summary['both_profiles_complete_before_annual_scoring'] is complete,'all-profile annual gate')
 if complete:
  check(summary['status']=='IVOL_REGIME_RAW_PRE2026_DAILY_ENGINEERING_COMPLETE','complete engineering status')
  for b in (20,40):
   reconstructed=metrics(data_by_bps[b]);actual=summary['results_by_extra_bps'][str(b)]
   for k,v in reconstructed.items():check(isclose(actual[k],v,rel_tol=1e-12,abs_tol=1e-10),'independent continuous annual/exposure/drawdown/cost '+k)
   profiles[str(b)]['independently_recomputed_metrics']=reconstructed
  m=profiles['40']['independently_recomputed_metrics'];gate=m['2024_return_pct']>0 and m['2025_return_pct']>0 and m['average_exposure_pct']>=90
  check(summary['raw_daily_proxy_development_gate_passes'] is gate,'fixed40bp pre2026 gate independently reproduced')
 else:
  check(summary['status']=='IVOL_REGIME_RAW_PRE2026_FAILED_OR_INCOMPLETE_PRESERVED' and summary['raw_daily_proxy_development_gate_passes'] is False,'failed account cannot be promoted')
 controls=negative_controls(data_by_bps[20],20,events,sessions,targets,bars,evidence,allcodes,record_by_bps[20],lifecycles)
 for n,h in known.items():check(sha(n)==h,'all inputs remain unchanged after independent read-only audit')
 report={'status':'PASS_INDEPENDENT_REGIME_DAILY_ACCOUNT_AUDIT' if complete else 'PASS_INDEPENDENT_FAILED_REGIME_ACCOUNT_PRESERVATION_AUDIT','summary_sha256':sha(root/'summary.json'),'plan_sha256':a.expected_plan_sha256,'freeze_commit':subprocess.check_output(['git','rev-parse',a.freeze_commit],cwd=repo,text=True).strip(),'audit_code_sha256':sha(__file__),'all_profile_daily_ledgers_independently_reconstructed':True,'both_profiles_complete':complete,'all_completed_phases_independently_reconstructed':True,'results_by_extra_bps':profiles,'source_summary_sha256':sa['source_summary_sha256'],'source_audit_sha256':sha(repo/SOURCE_AUDIT),'original_failure_audit_sha256':sha(repo/OLD_AUDIT),'primary_original_source_proof':primaryproof,'all_output_file_sha256':{str(f.relative_to(root)):sha(f) for f in sorted(root.rglob('*')) if f.is_file()},'all_bound_inputs_actual_sha256':known,'old42_financial_sha256':sa['old42_financial_sha256'],'old_failure_output_artifact_sha256':oldaudit['all_output_file_sha256'],'semantic_negative_controls_rejected':controls,'imports_project_code':False,'account_replay_rerun':False,'production_scorer_called':False,'portfolio_returns_computed_by_audit':complete,'2026_source_or_results_read':False,'network_used':False,'production_or_source_modified':False,'original_ordinary_guard_bypassed':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['DAILY_PROXY engineering accounting only; no intraday/order-queue or actual historical source-arrival certification.','ST rule/source metadata and actual original bytes are bound; the conservative engineering availability proxy is not actual historical arrival.','If the actual account has no ST orders, limit-order/permission handling is supported only by separate synthetic tests, not real-account exercise.','Six unresolved tax events remain unverified; only actual reconstructed zero record/ex quantities permit their passage. Actual FIFO tax settlement remains unsupported.','No2026 observations, returns, strategy attribution, ticker filtering or altered target weights were used.']}
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps({'status':report['status'],'report':str(out),'report_sha256':sha(out),'audit_code_sha256':sha(__file__),'both_complete':complete}))
if __name__=='__main__':main()
