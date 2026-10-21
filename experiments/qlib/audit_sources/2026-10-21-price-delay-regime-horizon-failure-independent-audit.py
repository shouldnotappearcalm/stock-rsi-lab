"""Independent bounded failed price-delay regime account audit.
Stdlib only. No production imports, replay, scoring, network or annual ROI.
Only source bars through the last completed session are decoded.
"""
from pathlib import Path
from decimal import Decimal as D, ROUND_HALF_UP, ROUND_DOWN
from collections import defaultdict,Counter
import argparse,copy,csv,hashlib,json,subprocess
from datetime import datetime,timezone,timedelta
from math import isclose
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


from datetime import datetime,timezone,timedelta
import io,re
PRE='2025-12-31';FAILED='2026-06-04';LAST='2026-06-03';LOCAL=timezone(timedelta(hours=8))
RUN='price-delay-regime-raw-daily-horizon-20261021';OLD_RUN='price-delay-raw-daily-horizon-20261021'
RAW='price-delay-raw-horizon-v2-20261021';SOURCE='price-delay-account-horizon-events-20261021'
OLD_DAILY='price-delay-raw-daily-pre2026-20261021';OLD_INTRA='price-delay-intraday-pre2026-20261021'
OLD_PLAN='experiments/qlib/price-delay-horizon-raw-daily-request.json'
EVIDENCE='experiments/qlib/price-delay-regime-horizon-evidence.json'
PRIMARY='price-delay-regime-primary-horizon-20261021'
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(v):return hashlib.sha256(canon(v).encode()).hexdigest()
def clock(d,t):return datetime.fromisoformat(d+'T'+t).replace(tzinfo=LOCAL).astimezone(timezone.utc).isoformat()
def no_annual(value):
 if isinstance(value,list):
  for v in value:no_annual(v)
 elif isinstance(value,dict):
  for k,v in value.items():
   check('return_pct' not in k and k not in ('average_exposure_pct','max_drawdown_pct','ending_equity','2026_starting_equity','three_numeric_conditions_met_at_interim_cutoff'),'failure evidence cannot publish aggregate return/exposure')
   no_annual(v)
def read_bounded_bars(path,last):
 """Hash the complete original separately; decode only literal bars <=last."""
 text=Path(path).read_text();match=re.search(r'"bars"\s*:\s*\[',text);check(match is not None,'original raw bars array')
 index=match.end();decoder=json.JSONDecoder();out={}
 while True:
  while text[index].isspace() or text[index]==',':index+=1
  if text[index]==']':break
  date_match=re.search(r'"date"\s*:\s*"(\d{4}-\d{2}-\d{2})"',text[index:index+160]);check(date_match is not None,'literal source row date precedes quote parsing')
  if date_match.group(1)>last:break
  row,end=decoder.raw_decode(text,index);check(row['date']==date_match.group(1) and row['date'] not in out,'bounded unique raw date');out[row['date']]=row;index=end
 return out

def fractional_dependency(state,part,event,sessions):
 check(state['last_account_clock']==[LAST,1] and part['rows'][-1]['day']==LAST and len(part['rows'])==584,'failure before Jun4 daily clock mutation')
 check([r['day'] for r in part['rows']]==sessions[:sessions.index(FAILED)],'continuous584completed sessions')
 check(event['instrument']=='SZ002831' and event['recorded']==LAST and event['ex_date']==FAILED,'exact primary-sourced failed event dates')
 q=state['entitlements'][event['event_id']];check(type(q) is int and q==900,'actual registered900 shares')
 actual=[r for r in state['corporate_ledger'] if r['event_id']==event['event_id'] and r['kind']=='RECORD_DATE_OWNERSHIP'];check(len(actual)==1 and actual[0]['day']==LAST and actual[0]['quantity']==q,'one actual failing-event record ownership')
 check(part['ownership'][LAST][event['instrument']]==q==state['owned_shares'][event['instrument']],'registered versus actual closing integer shares')
 cap=D(event['capital_per_share'])*q;stock=D(event['stock_per_share'])*q
 check(D(event['capital_per_share'])==D('0.4019063') and event['capital_tax_exempt_verified'] is True,'original precision contract and limited tax flag unchanged')
 check(cap==D('361.7156700') and cap!=cap.to_integral_value() and stock==0,'exact noninteger capital entitlement triggers original registry guard')
 check(all(r['day']<FAILED for r in state['corporate_ledger']) and all(f['execution_at'][:10]<FAILED for f in state['fills']),'no failing-day credits, registry entries, listed shares or fills')
 check(not any(c['event_id']==event['event_id'] for c in state['cash_claims']+state['stock_claims']),'failed event created no cash or stock claim')
 check(D(state['cash'])==D(part['rows'][-1]['cash']),'failureday cash remains last completed cash')
 due=[c for c in state['cash_claims'] if not c['paid'] and c['available_on']==FAILED]
 return {'event_id':event['event_id'],'instrument':event['instrument'],'recorded':LAST,'ex_date':FAILED,'registered_quantity':q,'cash_per_original_share_CNY':event['cash_per_share'],'capital_per_original_share':event['capital_per_share'],'exact_capital_share_entitlement':str(cap),'unresolved_fractional_share_component':str(cap%1),'stock_share_entitlement':str(stock),'capital_tax_flag_preserved':True,'failed_before_any_June4_account_mutation':True,'due_cash_claim_count_not_credited':len(due),'due_net_cash_not_credited_CNY':str(sum((D(c['net']) for c in due),D(0))),'rounding_flooring_or_registry_allocation_invented':False}

def applicable(code,day,when,evidence):
 states=[s for s in evidence['state_intervals'] if s['instrument']==code and s['effective_from']<=day<=s['effective_through']];epochs=[e for e in evidence['rule_epochs'] if e['valid_from']<=day<=e['valid_through']]
 check(len(states)==len(epochs)==1,'one applicable original issuer state and rule epoch')
 state,epoch=states[0],epochs[0];at=datetime.fromisoformat(when)
 check(datetime.fromisoformat(state['engineering_available_at'])<=at and datetime.fromisoformat(epoch['engineering_available_at'])<=at and state['published_on']<state['effective_from'],'conservative state/rule availability before execution')
 check(state['actual_arrival_verified'] is False and epoch['actual_arrival_verified'] is False and state['exchange']=='SSE' and state['board']=='MAINBOARD','no source arrival or board upgrade')
 check((epoch['valid_from'],epoch['valid_through'],epoch['limit_ratio']) in [('2023-12-29','2026-07-05','0.05'),('2026-07-06','2026-10-20','0.10')],'frozen 5/10percent source epochs')
 return epoch
def bands(reference,ratio):
 r=D(reference);t=D(ratio);up=cents(r*(1+t));down=cents(r*(1-t));return max(up,r+D('.01')),max(D('.01'),min(down,r-D('.01')))

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
    epoch=applicable(c,day,clock(day,'09:25:00'),evidence);upper,lower=bands(reference,epoch['limit_ratio']);check(lower<=price<=upper,'ST actual opening inside statutory five-percent band')
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
  uncertain=D(e['capital_per_share'])>0 and not e['capital_tax_exempt_verified'] or D(e['stock_per_share'])>0 and not e['stock_tax_basis_verified']
  if uncertain and e['ex_date'] in complete_days:
   rr=[r for r in data['corporate_ledger'] if r['event_id']==e['event_id'] and r['kind']=='RECORD_DATE_OWNERSHIP'];xx=[r for r in data['corporate_ledger'] if r['event_id']==e['event_id'] and r['kind']=='EX_DATE_ENTITLEMENT']
   check(len(rr)==len(xx)==1 and rr[0]['quantity']==xx[0]['registered_quantity']==0,'unresolved tax event only passes with actual zero registry ownership')
   unknown.append({'event_id':e['event_id'],'instrument':e['instrument'],'ex_date':e['ex_date'],'actual_record_and_ex_quantity':0,'tax_state_upgraded':False})
 for e in events:
  for kind,dayfield in (('RECORD_DATE_OWNERSHIP','recorded'),('EX_DATE_ENTITLEMENT','ex_date')):
   if e[dayfield] in complete_days:check(sum(x['event_id']==e['event_id'] and x['kind']==kind for x in cd[e[dayfield]])==1,'every due event record/ex exactly once')
 for intent in data['intents']:
  execution=intent['execution_session'];asof=intent['as_of'][:10];check(asof==sessions[sessions.index(execution)-1]==targets[execution]['as_of'],'priorclose next-session intent')
  check(intent['owned_integer_shares']==daily_owned[asof],'intent actual owned integer inventory');check(D(intent['equity_at_decision'])==D(next(x['equity'] for x in data['days'] if x['day']==asof)),'priorclose account equity')
  # Independently calculate the unchanged nonbudgeted per-name floors.
  actualday=next(x for x in data['days'] if x['day']==asof);equity=D(actualday['equity']);own=daily_owned[asof];expected=[]
  for code in sorted(set(own)|set(targets[execution]['weights'])):
   held=own.get(code,0);weight=D(str(targets[execution]['weights'].get(code,0)))
   if not weight:quantity=held;action='SELL'
   else:
    mark=D(bars(code)[asof]['close']);desired=int((equity*weight/mark/100).to_integral_value(rounding=ROUND_DOWN))*100
    if desired>held:quantity=(desired-held)//100*100;action='BUY'
    else:quantity=held-desired;action='SELL'
   if quantity:expected.append((action,code,quantity))
  expected.sort(key=lambda x:(x[0]!='SELL',x[1]));check([(d['action'],d['security_id'],d['quantity']) for d in intent['decisions']]==expected,'all30 fixed physical target integer quantities')
  check('allocation_receipt' not in intent,'nonbudgeted original intent shape retained')
 return {'daily_rows_reconstructed':len(complete_days),'monthly_intents_reconstructed':len(data['intents']),'fills_reconstructed':len(data['fills']),'corporate_records_reconstructed':len(data['corporate_ledger']),'cash_reconstructed_CNY':str(cash),'signed_fill_notional_CNY':str(signed_total),'fill_costs_CNY':str(fees_total),'net_cash_credits_CNY':str(cashcredits),'final_integer_listed_lots':numeric_lots(lots),'final_pending_stock_claims':[x for x in stockclaims if not x['credited']],'observed_unknown_tax_zero_ownership':unknown,'actual_ST_owned_raw_marks':held_ST},records

def prefix_checks(base,part,state,original_daily_summary,cost):
 trace=read(base/OLD_RUN/str(cost)/'partial_case.json');oldstate=read(base/OLD_RUN/str(cost)/'failed_account_state.json');cut='2026-03-31'
 check(len(trace['rows'])==541 and len(trace['intents'])==27,'old541/27 failure prefix is original evidence')
 check(part['rows'][:541]==trace['rows'] and [i for i in part['intents'] if i['execution_session']<cut]==trace['intents'],'old541cash/27intent literal prefix identical')
 check({d:v for d,v in part['ownership'].items() if d<cut}==trace['ownership'],'old541 integer ownership prefix')
 for k in ('fills','corporate_ledger'):
  field='execution_at' if k=='fills' else 'day';check([v for v in state[k] if v[field][:10]<cut]==oldstate[k],'old541 fill/corporate prefix '+k)
 checkpoint=state['pre2026_checkpoint'];folder=base/OLD_DAILY/str(cost);oldhash=original_daily_summary['results_by_extra_bps'][str(cost)]['artifact_sha256']
 days=[x for x in part['rows'] if x['day']<=PRE];check(len(days)==486,'all486pre2026source days remain');stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(days[0]));writer.writeheader();writer.writerows(days);reproduced={'daily.csv':hashlib.sha256(stream.getvalue().encode()).hexdigest()}
 with (folder/'daily.csv').open(newline='') as f:check(list(csv.DictReader(f))==days,'old486 actual daily CSV exact')
 objects={k:checkpoint[k] for k in ('orders','fills','corporate_ledger')};objects['intents']=[i for i in part['intents'] if i['execution_session']<=PRE];objects['ownership']={d:v for d,v in part['ownership'].items() if d<=PRE};check(len(objects['intents'])==24,'all24 old frozen intentions')
 for k,v in objects.items():check(read(folder/(k+'.json'))==v,'old original checkpoint/intent/ownership '+k);reproduced[k+'.json']=hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest()
 check(reproduced==oldhash,'old six serialized financial SHA prefixes identical')
 rawscope=read(base/'price-delay-ordinary-source-scope-20261021/scope.json')['nonordinary_source_intervals'];expected=[{'instrument':r['instrument'],'session':r['day'],'reason':'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT','original_row_present':True,'source_isST':'1','required_by_account':False,'synthetic_price_created':False} for r in rawscope]
 check(len(expected)==241 and [r for r in part['lifecycle_audit'] if r['session']<=PRE]==expected,'all241 original unused nonordinary source scope evidence retained')
 return {'old541_days_27intents_fills_corporate_ownership_exact':True,'old486_days_24intents_six_financial_prefix_bytes_exact':True,'old241_source_scope_prefix_identical':True,'reconstructed_old6_prefix_sha256':reproduced}

def verify_ST_orders(state,bars,evidence):
 st=[];fillids={f['order_id'] for f in state['fills']}
 for f in state['fills']:
  row=bars(f['security_id'])[f['execution_at'][:10]];check(not(f['action']=='BUY' and row['isST']=='1'),'no unauthorized STBUY fill, including partial fills')
 for order in state['orders']:
  day=order['eligible_at'][:10];source=bars(order['security_id']).get(day)
  if source is None or source['isST']!='1':continue
  epoch=applicable(order['security_id'],day,clock(day,'09:25:00'),evidence);upper,lower=bands(source['preclose'],epoch['limit_ratio'])
  check(order['order_type']=='LIMIT' and order['trading_regime_contract']=='SSE_MAINBOARD_RISK_WARNING_HORIZON_V1' and D(order['limit_price'])==(upper if order['action']=='BUY' else lower),'actual ST order type/directional legal epoch limit')
  if order['action']=='BUY':check(evidence['account_capabilities']['risk_warning_buy_permission'] is False and order['status']=='UNFILLED_RISK_WARNING_PERMISSION' and order['order_id'] not in fillids,'actual STBUY permission refusal without fill')
  st.append({'order_id':order['order_id'],'instrument':order['security_id'],'execution_session':day,'action':order['action'],'requested_quantity':order['quantity'],'status':order['status'],'limit_price':order['limit_price'],'rule_limit_ratio':epoch['limit_ratio'],'source_preclose':source['preclose']})
 check(len(st)==2 and {x['execution_session'] for x in st}=={'2026-04-01','2026-06-01'} and all(x['instrument']=='SH600079' for x in st),'two actual STpermission refusals before independent fractional guard')
 return st

def negative(fn):
 try:fn()
 except (AssertionError,ValueError,KeyError):return True
 raise AssertionError('semantic negative accepted')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('source-root','repo-root','plan','expected-plan-sha256','freeze-commit','output'):p.add_argument('--'+n,required=True)
 p.add_argument('--terminal-confirmed',action='store_true');a=p.parse_args();check(a.terminal_confirmed,'actual terminal confirmation mandatory')
 base,repo,out=map(lambda s:Path(s).resolve(),(a.source_root,a.repo_root,a.output));root=base/RUN;planpath=Path(a.plan).resolve()
 check(not out.exists() and not out.is_relative_to(base) and not out.is_relative_to(repo),'new external audit report')
 check(sha(planpath)==a.expected_plan_sha256,'external frozen regime request');plan=read(planpath);known=read(root/'input-before.json');summary=read(root/'summary.json');post=read(root/'input-postcheck.json')
 check(summary['plan_sha256']==a.expected_plan_sha256 and summary['all_profiles_complete_before_returns'] is False and summary['execution_model']=='DAILY_PROXY_ONLY','actual failed daily proxy scope')
 check(plan['status']=='FROZEN_UNCHANGED_PRICE_DELAY_SSE_REGIME_HORIZON' and plan['allocator']=='plan_integer_targets' and plan['risk_warning_buy_permission'] is False and plan['extra_cost_bps']==[20,40] and plan['initial_CNY']=='1000000','fixed original method/permission/capital/costs')
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for n,h in plan[field].items():
   check(sha(parent/n)==h==known[str((parent/n).resolve())],'actual frozen plan input '+n)
   if parent==repo:check(hashlib.sha256(subprocess.check_output(['git','show',a.freeze_commit+':'+n],cwd=repo)).hexdigest()==h,'frozen method/public blob '+n)
 check(hashlib.sha256(subprocess.check_output(['git','show',a.freeze_commit+':'+str(planpath.relative_to(repo))],cwd=repo)).hexdigest()==a.expected_plan_sha256,'frozen request blob')
 for n,h in known.items():check(sha(n)==h,'all before/after actual input SHA unchanged')
 check(post=={'all_bound_inputs_unchanged':True,'source_authentication_repeated':True,'errors':[],'completed':True} and summary['postcheck']=={**post,'persistence_errors':[]},'actual full repeated sourceauth and immutable input postcheck')
 for f in ('investment_rule_changed','old_failure_relabelled_success','full_October_2026_complete','sealed_2026_evidence_claimed','historical_arrival_verified','queue_and_impact_calibrated','actual_FIFO_tax_liability_verified','candidate_promoted','objective_achieved'):check(summary[f] is False,'failure/evidence boundary '+f)
 check(summary['source_queries']==0 and summary['old60_financial_files_unchanged'] is True and summary['risk_warning_buy_permission'] is False,'source-only originals retained')
 cases=read(root/'case_results.json');check(cases==summary['results_by_extra_bps'] and set(cases)=={'20','40'},'both failed cost profiles retained');no_annual(summary);no_annual(cases)
 original=read(repo/OLD_PLAN);financial=original['immutable_financial_sha256'];check(len(financial)==60,'all60 original financial inputs')
 for n,h in financial.items():check(sha(base/n)==h==known[str((base/n).resolve())],'old60 actual audited financial byte identity')
 oldfa=read(repo/'experiments/qlib/price-delay-horizon-raw-account-failure-independent-review.json');check(oldfa['status']=='INDEPENDENT_BOUNDED_RAW_ACCOUNT_FAILURE_EVIDENCE_CONFIRMED_NO_ANNUAL_ROI' and oldfa['summary_sha256']==sha(base/OLD_RUN/'summary.json') and oldfa['case_results_sha256']==sha(base/OLD_RUN/'case_results.json'),'old original failure independent anchor')
 oldfiles={OLD_RUN+'/summary.json':oldfa['summary_sha256'],OLD_RUN+'/case_results.json':oldfa['case_results_sha256']}
 for label,profile in oldfa['profiles'].items():
  for n,h in profile['failure_artifact_sha256'].items():oldfiles[OLD_RUN+'/'+label+'/'+n]=h
 check(len(oldfiles)==10,'original10 failure artifacts')
 for n,h in oldfiles.items():check(sha(base/n)==h==known[str((base/n).resolve())],'all10 original failure bytes unchanged')
 rm=read(base/RAW/'manifest.json');sessions=read(base/RAW/'calendar.json')['sessions'];check(len(sessions)==676 and sessions[:486]==read(base/'price-delay-raw-dev-20261021/calendar.json')['sessions'] and sha(base/RAW/'calendar.json')==rm['calendar_sha256'],'immutable676explicit/old486calendar')
 raw={}
 for code,h in rm['per_code_sha256'].items():
  path=base/RAW/'codes'/(code+'.json');check(sha(path)==h==known[str(path.resolve())],'original full203 source packet bytes');raw[code]=read_bounded_bars(path,LAST)
 check(len(raw)==203,'all203 original source packet identities')
 targets=read(base/'price-delay-horizon-formations-20261021/candidate_targets.json');check(len(targets)==34,'unchanged34 fixed monthly targets');events=read(base/SOURCE/'derived_events.json');check(len(events)==613,'fixed613 independently admitted source events')
 eventaudit=read(repo/'experiments/qlib/price-delay-horizon-event-source-independent-audit.json');ss=read(base/SOURCE/'summary.json');check(eventaudit['summary_sha256']==sha(base/SOURCE/'summary.json') and eventaudit['events_reconstructed']==613 and eventaudit['imports_project_code'] is False and not eventaudit['critical_or_important_findings'],'independent full source event proof anchor')
 for n,h in ss['artifact_sha256'].items():check(sha(base/SOURCE/n)==h==known[str((base/SOURCE/n).resolve())],'compiled source proof/receipt artifact SHA')
 evidence=read(repo/EVIDENCE);primary=read(base/PRIMARY/'manifest.json');check(primary==read(repo/'experiments/qlib/price-delay-regime-primary-source-manifest.json') and primary['reviewed_regime_evidence']==evidence,'frozen original primary review and evidence identity')
 for n,h in primary['artifact_sha256'].items():check(sha(base/PRIMARY/n)==h==known[str((base/PRIMARY/n).resolve())],'all actual primary original bytes')
 check(evidence['contract']=='SSE_MAINBOARD_RISK_WARNING_HORIZON_V1' and evidence['account_capabilities']=={'risk_warning_buy_permission':False} and [(e['valid_from'],e['valid_through'],e['limit_ratio']) for e in evidence['rule_epochs']]==[('2023-12-29','2026-07-05','0.05'),('2026-07-06','2026-10-20','0.10')] and evidence['rule_epochs'][1]['published_on']=='2026-04-24','fixed source-authenticated SSE epochs and no synthetic signature')
 event=next(e for e in events if e['instrument']=='SZ002831' and e['ex_date']==FAILED);oldsummary=read(base/OLD_DAILY/'summary.json');profiles={};first=None
 for cost in (20,40):
  folder=root/str(cost);result=cases[str(cost)];check(result['status']=='INVALID_SOURCE_OR_ACCOUNT' and result['error_type']=='ValueError' and result['error']=='fractional corporate entitlement needs registry allocation evidence' and result['portfolio_returns_computed'] is False,'preserved same fractional registry guard')
  check({x.name:sha(x) for x in folder.iterdir() if x.is_file()}==result['failure_artifact_sha256'] and set(result['failure_artifact_sha256'])=={'error.json','failed_account_state.json','partial_case.json','source_scope_audit.json'},'every failure file SHA and exact four-file scope')
  check(read(folder/'error.json')=={k:result[k] for k in ('status','error_type','error','portfolio_returns_computed')},'original exact error.json and terminal summary linkage')
  part=read(folder/'partial_case.json');state=read(folder/'failed_account_state.json');scope=read(folder/'source_scope_audit.json');check(scope==part['lifecycle_audit'],'preserved scope trail identical')
  data={'days':part['rows'],'intents':part['intents'],'ownership':part['ownership'],**{k:state[k] for k in ('orders','fills','corporate_ledger')}}
  dependency=fractional_dependency(state,part,event,sessions)
  ledger,records=audit_profile(data,cost,events,sessions,targets,lambda c:raw[c],evidence,sorted(raw),state)
  ledger.pop('final_integer_listed_lots');ledger.pop('final_pending_stock_claims');ledger.pop('actual_ST_owned_raw_marks')
  check(len(data['intents'])==30 and len(part['rows'])==584,'no fabricated full676/34 completion')
  profiles[str(cost)]={'fractional_dependency':dependency,'last_account_clock':state['last_account_clock'],'independent_partial_ledger':ledger,'prefix_checks':prefix_checks(base,part,state,oldsummary,cost),'actual_ST_limit_permission_orders':verify_ST_orders(state,lambda c:raw[c],evidence),'annual_returns_computed':False}
  no_annual(read(folder/'error.json'))
  if first is None:first=(state,part,data,records)
 state,part,data,records=first;negatives={}
 changed=copy.deepcopy(event);changed['capital_per_share']='0.4';negatives['rounded_source_ratio_cannot_explain_failure']=negative(lambda:fractional_dependency(state,part,changed,sessions))
 changed=copy.deepcopy(state);changed['entitlements'][event['event_id']]=1000;negatives['changed_record_quantity_rejected']=negative(lambda:fractional_dependency(changed,part,event,sessions))
 changed=copy.deepcopy(state);changed['last_account_clock']=[FAILED,0];negatives['failureday_clock_mutation_rejected']=negative(lambda:fractional_dependency(changed,part,event,sessions))
 changed=copy.deepcopy(summary);changed['2026_through_2026-10-20_return_pct']=0;negatives['failed_account_annual_ROI_field_rejected']=negative(lambda:no_annual(changed))
 changed=copy.deepcopy(data);changed['fills'][0]['cost']=str(D(changed['fills'][0]['cost'])+D('.01'));negatives['independent_fill_fee_mismatch_rejected']=negative(lambda:audit_profile(changed,20,events,sessions,targets,lambda c:raw[c],evidence,sorted(raw),None))
 for n,h in known.items():check(sha(n)==h,'all bound inputs unchanged after this read-only independent audit')
 allfiles={str(f.relative_to(root)):sha(f) for f in sorted(root.rglob('*')) if f.is_file()};check(len(allfiles)==13,'exact13preserved output files')
 report={'status':'PASS_INDEPENDENT_BOUNDED_PRICE_DELAY_REGIME_FRACTIONAL_GUARD_FAILURE_AUDIT','verdict':'FAILED_REGISTRY_ALLOCATION_ADMISSION_CORRECTLY_PRESERVED_NO_ANNUAL_ROI','audit_code_sha256':sha(__file__),'plan_sha256':a.expected_plan_sha256,'freeze_commit':subprocess.check_output(['git','rev-parse',a.freeze_commit],cwd=repo,text=True).strip(),'summary_sha256':sha(root/'summary.json'),'case_results_sha256':sha(root/'case_results.json'),'failure_day':FAILED,'failure_instrument':'SZ002831','failure_event_id':event['event_id'],'profiles':profiles,'all_completed584_daily_ledgers_independently_reconstructed':True,'all_old60_financial_bytes_unchanged':True,'all_old10_failure_files_unchanged':True,'all_actual_input_hashes_verified_before_after':True,'actual_input_count':len(known),'all_output_file_sha256':allfiles,'old60_financial_sha256':financial,'old10_failure_artifact_sha256':oldfiles,'all_bound_input_sha256':known,'event_source_summary_sha256':sha(base/SOURCE/'summary.json'),'event_source_independent_audit_sha256':sha(repo/'experiments/qlib/price-delay-horizon-event-source-independent-audit.json'),'primary_manifest_sha256':sha(base/PRIMARY/'manifest.json'),'semantic_negative_controls_rejected':negatives,'imports_project_code':False,'account_replay_or_annual_scorer_called':False,'portfolio_returns_computed':False,'source_or_target_modified':False,'network_or_new_source_queries':False,'original_ordinary_failure_relabelled_success':False,'full676day_account_claimed':False,'full_October_2026_complete':False,'sealed_2026_evidence_claimed':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['Observed584sessions endJune3; June4 fails before account.start_day mutation because900registered shares times0.4019063 equals361.7156700capital shares. No registry allocation, flooring, or rounding is invented.','No annual2024/25/2026 return, average exposure, drawdown or full676day continuation is calculated or certified. Partial daily net_return fields are retained accounting evidence only.','Two actual daily-proxy account STBUY LIMIT requests onApr1/Jun1 are verified as permission refusals with nofill. The account never reachesJuly6: actual10percent execution is not exercised.','Failure serializer does not retain complete regime/phase audit histories. Clock order is established from authenticated frozen methods plus saved lastphase and absence of June4 ledger/fill/claim mutation; full daily phase-history verification is not claimed.','Only source bars throughJune3 are JSON-decoded; complete original packet bytes and allbound inputs are authenticated by hash. No future quote/return analysis or strategy attribution is performed.','This is DAILY_PROXY accounting and limited source evidence, not minute execution, queue/impact or actual FIFO tax certification.']}
 out.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n');print(json.dumps({'status':report['status'],'output':str(out),'report_sha256':sha(out),'audit_code_sha256':sha(__file__),'failure_day':FAILED,'event':event['event_id'],'partial_days':584}))
if __name__=='__main__':main()
