"""Independent Decimal reconciliation of a complete physical registry leaf.

This validator never runs an account, allocation choice search or return scorer.
Original integer/cash/tax/T+1/FIFO/fee/mark checks remain separate from the one
new allowance: an explicitly audited entire-account integer candidate for each
noninteger capital or stock entitlement. Primary bytes are caller-authenticated.
"""
from collections import defaultdict, Counter
from decimal import Decimal as D, ROUND_HALF_UP
from fractions import Fraction
from datetime import date, datetime, time, timedelta, timezone
import json

from stock_rsi.registry_allocation_bounds import allocation_bounds

CAPITAL='1000000'
AUDIT_FIELDS=frozenset({'event_id','instrument','recorded','ex_date','component',
 'registered_quantity','ratio_per_original_share','nominal_entitlement','candidates',
 'chosen_integer_quantity','registry_proof_sha256','as_of','envelope'})


def need(value,message):
 if not value:raise ValueError(message)


def _opening(event):return event.ex_date.isoformat()+'T09:30:00+08:00'


def _ratio(event,component):
 return event.capital_per_share if component=='capital' else event.stock_per_share


def _bound_proof(event,component,proof,quantity):
 envelope=allocation_bounds(proof,quantity,as_of=_opening(event))
 ratio=_ratio(event,component)
 need(proof['event_id']==event.event_id and proof['issuer']==event.instrument
      and proof['component']==component and proof['record_date']==event.recorded.isoformat()
      and proof['ex_date']==event.ex_date.isoformat()
      and proof['published_on']==event.announced.isoformat()
      and ratio>0 and Fraction(proof['quoted_per10'])/10==Fraction(ratio),
      'primary proof must match unchanged event identity, dates and component ratio')
 return envelope


def _index_allocations(case,events,proofs):
 byid={event.event_id:event for event in events}
 need(len(byid)==len(events),'unique immutable event identities required')
 need(type(proofs) is dict,'explicit primary registry proof map required')
 for event_id,components in proofs.items():
  need(event_id in byid and type(components) is dict and bool(components)
       and set(components)<= {'capital','stock'},'orphan or unsupported primary registry proof')
  for component,proof in components.items():_bound_proof(byid[event_id],component,proof,0)
 rows=case.get('registry_allocation_audit',[])
 need(type(rows) is list,'explicit registry allocation audit list required')
 audits={}
 for row in rows:
  need(type(row) is dict and set(row)==AUDIT_FIELDS,'exact registry allocation audit fields required')
  need(row['event_id'] in byid and row['component'] in ('capital','stock'),
       'orphan event or component allocation audit')
  key=(row['event_id'],row['component'])
  need(key not in audits,'duplicate registry component allocation audit')
  audits[key]=row
 return audits,set()


def _allocated_quantity(event,component,quantity,nominal,proofs,audits,consumed):
 key=(event.event_id,component)
 need(type(quantity) is int and quantity>=0,'actual registered quantity must be a nonnegative integer')
 if nominal==nominal.to_integral_value():
  need(key not in audits,'original integer entitlement cannot acquire an allocation override')
  return int(nominal)
 need(key in audits and component in proofs.get(event.event_id,{}),
      'noninteger component requires one primary-bound allocation audit')
 row=audits[key];envelope=_bound_proof(event,component,proofs[event.event_id][component],quantity)
 chosen=row['chosen_integer_quantity'];candidates=row['candidates']
 need(type(candidates) is list and all(type(n) is int for n in candidates)
      and candidates==envelope['possible_integer_shares']
      and type(chosen) is int and chosen in candidates,'chosen strict integer must belong to entire-account envelope')
 need(type(row['registered_quantity']) is int and row['registered_quantity']==quantity
      and row['instrument']==event.instrument and row['recorded']==event.recorded.isoformat()
      and row['ex_date']==event.ex_date.isoformat()
      and row['ratio_per_original_share']==str(_ratio(event,component))
      and row['nominal_entitlement']==str(nominal)
      and row['registry_proof_sha256']==envelope['proof_sha256']
      and row['as_of']==_opening(event),'allocation audit differs from original event, quantity, ratio, proof or clock')
 # JSON tuples and arrays represent the same exact rational-pair metadata.
 canonical=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
 need(type(row['envelope']) is dict and canonical(row['envelope'])==canonical(envelope),
      'complete primary envelope or uncertified evidence flags changed')
 need(key not in consumed,'noninteger component credited more than once')
 consumed.add(key)
 return chosen


def _complete_timeline(case,events,sessions):
 """Require the entire observed stream and every scheduled source event."""
 need(bool(sessions) and all(type(d) is str and date.fromisoformat(d).isoformat()==d for d in sessions)
      and list(sessions)==sorted(set(sessions)),'explicit ordered unique calendar required')
 allowed=set(sessions);byid={event.event_id:event for event in events}
 corp=defaultdict(list);fills=defaultdict(list);counts=Counter()
 phases={'NET_DIVIDEND_CASH_AVAILABLE':0,'EX_DATE_ENTITLEMENT':1,
         'CAPITAL_SHARES_LISTED':2,'STOCK_DIVIDEND_SHARES_LISTED':2,'RECORD_DATE_OWNERSHIP':3}
 local=timezone(timedelta(hours=8))
 for row in case['corporate_ledger']:
  raw_day=row['day'];day=str(raw_day);kind=row['kind'];event_id=row['event_id']
  need(type(raw_day) in (str,date) and day in allowed and kind in phases and event_id in byid,
       'corporate row outside explicit calendar or immutable source event')
  event=byid[event_id]
  if kind=='RECORD_DATE_OWNERSHIP':expected=event.recorded.isoformat()
  elif kind=='EX_DATE_ENTITLEMENT':expected=event.ex_date.isoformat()
  elif kind=='NET_DIVIDEND_CASH_AVAILABLE':
   need(event.pay_date is not None,'cash credit without original payment date')
   expected=next((d for d in sessions if d>event.pay_date.isoformat()),None)
  else:
   need(event.listed is not None,'stock credit without original listing date')
   expected=next((d for d in sessions if d>=event.listed.isoformat()),None)
  need(day==expected,'corporate record/ex/payment/listing must use exact original first-session clock')
  if kind in ('RECORD_DATE_OWNERSHIP','EX_DATE_ENTITLEMENT'):
   need(row.get('instrument')==event.instrument,'corporate issuer must match original event')
  elif 'instrument' in row:need(row['instrument']==event.instrument,'corporate issuer identity changed')
  counts[(event_id,kind)]+=1
  need(counts[(event_id,kind)]==1,'duplicate source corporate event/component flow')
  corp[day].append(row)
 for event in events:
  for kind,when in (('RECORD_DATE_OWNERSHIP',event.recorded),('EX_DATE_ENTITLEMENT',event.ex_date)):
   if when.isoformat() in allowed:
    need(counts[(event.event_id,kind)]==1,'missing due record/ex source event, including zero ownership')
 for rows in corp.values():
  need([phases[row['kind']] for row in rows]==sorted(phases[row['kind']] for row in rows),
       'corporate flows must preserve start-day and end-day phase order')
 for fill in case['fills']:
  instant=datetime.fromisoformat(fill['execution_at'])
  need(instant.tzinfo is not None and instant.utcoffset() is not None,'aware actual execution timestamp required')
  day=instant.astimezone(local).date().isoformat()
  need(day in allowed and instant==datetime.combine(date.fromisoformat(day),time(9,30),tzinfo=local),
       'fill outside explicit calendar or daily opening clock')
  fills[day].append(fill)
 return byid,corp,fills


def reconcile_registry_case(case,events,bars,sessions,cost,*,registry_proofs):
 events=tuple(events)
 audits,consumed=_index_allocations(case,events,registry_proofs)
 need(type(cost) is int and cost in (20,40),'fixed integer cost profile required')
 need([r['day'] for r in case['days']]==sessions and set(case['ownership'])==set(sessions),'complete unique daily path')
 byid,corp,fills=_complete_timeline(case,events,sessions)
 consumed_corporate=0;consumed_fills=0
 cash=D(CAPITAL);previous_equity=cash;lots={};pending=[];claims={};registered={};marks={}
 for row in case['days']:
  day=row['day'];fees=D(0);paid=D(0)
  # No scheduled payment can remain hidden in receivables after its due day.
  due={event_id for event_id,claim in claims.items() if claim['available']==day}
  observed={r['event_id'] for r in corp[day] if r['kind']=='NET_DIVIDEND_CASH_AVAILABLE'}
  need(due==observed,'all due next-session cash claims must be paid exactly once')
  # Opening corporate rows precede trading; record ownership follows trading.
  for r in corp[day]:
   consumed_corporate+=1
   if r['kind']=='RECORD_DATE_OWNERSHIP':continue
   e=byid[r['event_id']];k=r['kind']
   if k=='NET_DIVIDEND_CASH_AVAILABLE':
    claim=claims.pop(e.event_id);need(claim['available']==day and r['cash_delta']==claim['net'],'cash availability conservation');cash+=claim['net'];paid+=claim['net']
   elif k=='EX_DATE_ENTITLEMENT':
    need(e.recorded.isoformat()<sessions[0] or e.event_id in registered,'recorddate must be observed');q=registered.get(e.event_id,0);need(r['registered_quantity']==q,'actualregisteredshares');capital_nominal=e.capital_per_share*q;stock_nominal=e.stock_per_share*q;capital=_allocated_quantity(e,'capital',q,capital_nominal,registry_proofs,audits,consumed);stock=_allocated_quantity(e,'stock',q,stock_nominal,registry_proofs,audits,consumed);need(not q or not e.capital_per_share or e.capital_tax_exempt_verified,'unknowncapitalguard');need(not q or not e.stock_per_share or e.stock_tax_basis_verified and e.stock_taxable_income_per_share>0,'unknownstockguard')
    gross=(e.cash_per_share*q).quantize(D('.01'),rounding=ROUND_HALF_UP);income=(e.stock_taxable_income_per_share*q).quantize(D('.01'),rounding=ROUND_HALF_UP);reserve=((gross+income)*D('.2')).quantize(D('.01'),rounding=ROUND_HALF_UP)
    need(reserve<=gross,'stock reserve exceeds cash');need(r['cash_gross']==gross and r['stress_tax_reserve']==reserve and r['capital_shares']==int(capital) and r.get('stock_shares',0)==int(stock) and r.get('taxable_stock_income',D(0))==income,'corporateeconomics')
    if gross:claims[e.event_id]={'net':gross-reserve,'available':next((d for d in sessions if d>e.pay_date.isoformat()),None)}
    for qty,kind in [(int(capital),'CAPITAL_SHARES_LISTED'),(int(stock),'STOCK_DIVIDEND_SHARES_LISTED')]:
     if qty:pending.append({'event_id':e.event_id,'instrument':e.instrument,'quantity':qty,'kind':kind,'listed':e.listed.isoformat(),'recorded':e.recorded.isoformat()})
   elif k in ('CAPITAL_SHARES_LISTED','STOCK_DIVIDEND_SHARES_LISTED'):
    matches=[p for p in pending if p['event_id']==e.event_id and p['kind']==k];need(len(matches)==1 and type(r['quantity']) is int and matches[0]['quantity']==r['quantity'] and next((d for d in sessions if d>=matches[0]['listed']),None)==day,'listedstockconservation');p=matches[0];pending.remove(p);lots.setdefault(e.instrument,[]).append({'quantity':p['quantity'],'bought_on':p['recorded']})
   else:raise ValueError('unknowncorporateledgerkind')
  need(not any(p['listed']<=day for p in pending),'all due stock claims must list on their exact first source session')
  byvolume=defaultdict(int)
  for f in fills[day]:
   consumed_fills+=1
   c=f['security_id'];q=f['quantity'];price=D(f['price']);source=bars[c][day]
   need(source['date']==day and source['tradestatus']=='1' and price.is_finite()
        and price>0 and price==price.quantize(D('.01')) and price==D(source['open']),
        'physical fill must match positive finite cent-tick open of the bound tradable session')
   need(type(q) is int and 0<q<=1000000 and f['action'] in ('BUY','SELL'),'physicalfill');gross=price*q;fee=max(D('5'),gross*D('0.0005' if f['action']=='BUY' else '0.0015')).quantize(D('.01'),rounding=ROUND_HALF_UP)+(gross*D(cost)/10000).quantize(D('.01'),rounding=ROUND_HALF_UP);need(D(f['cost'])==fee,'samebaseandextrafeeformula');fees+=fee;byvolume[c]+=q
   if f['action']=='BUY':need(q%100==0,'100sharebuy');cash-=gross+fee;lots.setdefault(c,[]).append({'quantity':q,'bought_on':day})
   else:
    need(sum(l['quantity'] for l in lots.get(c,[]) if l['bought_on']<day)>=q,'Tplus1FIFO');cash+=gross-fee;remain=q
    for l in lots.get(c,[]):
     if l['bought_on']>=day:continue
     used=min(l['quantity'],remain);l['quantity']-=used;remain-=used
    lots[c]=[l for l in lots[c] if l['quantity']]
    if not lots[c]:del lots[c]
   need(cash==D(f['cash_after']) and cash>=0,'fillcashconservation')
  for c,q in byvolume.items():need(D(bars[c][day]['volume'])>=q,'unsupported whole-day volume')
  listed={c:sum(l['quantity'] for l in ls) for c,ls in lots.items()}
  for r in corp[day]:
   if r['kind']=='RECORD_DATE_OWNERSHIP':need(type(r['quantity']) is int and r['quantity']==listed.get(r['instrument'],0),'recordownership');registered[r['event_id']]=r['quantity']
  for c in set(listed)|{p['instrument'] for p in pending}:
   source=bars[c][day]
   if source['tradestatus']=='1':marks[c]=D(source['close'])
   elif any(e.instrument==c and e.ex_date.isoformat()==day for e in events):marks[c]=D(source['preclose'])
   elif c not in marks:marks[c]=D(source['close'])
  mv=sum((q*marks[c] for c,q in listed.items()),D(0));pv=sum((p['quantity']*marks[p['instrument']] for p in pending),D(0));rv=sum((x['net'] for x in claims.values()),D(0));equity=cash+mv+pv+rv
  need(case['ownership'][day]==listed and row['cash']==cash and row['market_value']==mv and row['pending_stock_value']==pv and row['cash_receivable']==rv and row['equity']==equity and row['fees']==fees and row['net_dividend_cash_available']==paid,'dailycash/share/claims/equityconservation');need(equity.is_finite() and equity>0 and row['exposure']==(mv+pv)/equity and row['net_return']==equity/previous_equity-1,'dailyfinitepositiveequityandexposure');previous_equity=equity
 need(consumed_corporate==len(case['corporate_ledger']) and consumed_fills==len(case['fills']),'all source flows must be consumed exactly once')
 need(set(audits)==consumed,'orphan allocation audit without one observed noninteger component')
 return True
