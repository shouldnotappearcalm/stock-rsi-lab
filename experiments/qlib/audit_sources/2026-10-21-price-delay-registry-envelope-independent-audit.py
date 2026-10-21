"""Independent stdlib registry-tree and observed physical-ledger audit.
No project imports, simulator, driver, scorer, network or choice selection.
Actual output is inaccessible until --terminal-confirmed is explicitly passed.
"""
import argparse,copy,csv,hashlib,io,json,re,subprocess
from collections import Counter,defaultdict
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal as D,ROUND_HALF_UP,ROUND_DOWN
from fractions import Fraction
from math import isclose
from pathlib import Path
LOCAL=timezone(timedelta(hours=8));PRE='2025-12-31';START='2023-12-29';END='2026-10-20'
RUN='price-delay-registry-envelope-horizon-20261021';STRICT='price-delay-regime-raw-daily-horizon-20261021';ORIGINAL='price-delay-raw-daily-horizon-20261021'
RAW='price-delay-raw-horizon-v2-20261021';OLDRAW='price-delay-raw-dev-20261021';SOURCE='price-delay-account-horizon-events-20261021';OLDDAY='price-delay-raw-daily-pre2026-20261021'
PROOFS='experiments/qlib/price-delay-registry-allocation-proofs.json';EVIDENCE='experiments/qlib/price-delay-regime-horizon-evidence.json'
AUDIT_FIELDS={'event_id','instrument','recorded','ex_date','component','registered_quantity','ratio_per_original_share','nominal_entitlement','candidates','chosen_integer_quantity','registry_proof_sha256','as_of','envelope'}
def check(value,message):
 if not value:raise AssertionError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def canon(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canon(value).encode()).hexdigest()
def cents(value):return value.quantize(D('.01'),rounding=ROUND_HALF_UP)
def pair(value):return [str(value.numerator),str(value.denominator)]
def clock(day,when):return datetime.fromisoformat(day+'T'+when).replace(tzinfo=LOCAL).astimezone(timezone.utc).isoformat()
def no_ROI(value):
 if isinstance(value,list):
  for item in value:no_ROI(item)
 elif isinstance(value,dict):
  for key,item in value.items():
   check('return_pct' not in key and key not in ('2026_starting_equity','ending_equity','three_numeric_conditions_met_at_interim_cutoff'),'unscored/incomplete object contains annual ROI')
   no_ROI(item)
def clean(value):
 if isinstance(value,D):return str(value)
 if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [clean(v) for v in value]
 return value

def independent_bounds(proof,q,as_of):
 """Fraction reproduction of the frozen engineering envelope, no helper call."""
 fields={'contract','issuer','event_id','record_date','ex_date','component','source_file','source_sha256','published_on','available_at','actual_arrival_verified','eligible_count','declared_total_shares','quoted_per10','fraction_method','quoted_precision_bound'}
 check(type(proof) is dict and set(proof)==fields,'exact primary envelope proof schema')
 check(proof['contract']=='PRIMARY_LARGEST_REMAINDER_LOCAL_ENVELOPE_V1' and proof['fraction_method']=='LARGEST_REMAINDER_DESC_RANDOM_TIES' and proof['quoted_precision_bound']=='ONE_LAST_DIGIT_SYMMETRIC_ENGINEERING_ASSUMPTION','original largest-remainder and display assumptions')
 check(proof['actual_arrival_verified'] is False and proof['component'] in ('capital','stock') and re.fullmatch(r'(?:SH|SZ)[0-9]{6}',proof['issuer']) is not None,'proof issuer/component/arrival boundary')
 check(Path(proof['source_file']).name==proof['source_file'] and re.fullmatch('[0-9a-f]{64}',proof['source_sha256']) is not None,'primary basename and SHA')
 eligible,total=proof['eligible_count'],proof['declared_total_shares'];check(type(eligible) is type(total) is int and eligible>0 and total>0 and type(q) is int and 0<=q<=eligible,'entire registered quantity/global counts')
 check(proof['published_on']<=proof['record_date']<proof['ex_date'] and datetime.fromisoformat(proof['available_at'])<=datetime.fromisoformat(as_of),'primary source date/clock visibility')
 text=proof['quoted_per10'];check(type(text) is str and re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',text) is not None,'literal per10 decimal')
 quote=Fraction(text);check(quote>0,'positive per10');quantum=Fraction(1,10**(len(text.split('.')[1]) if '.' in text else 0));ratio=quote/10;exact=Fraction(total,eligible);lower,upper=(quote-quantum)/10,(quote+quantum)/10
 check(0<=lower<=exact<=upper,'declared ratio lies within fixed symmetric display envelope')
 lo,hi=q*lower,q*upper;first=lo.numerator//lo.denominator;last=-(-hi.numerator//hi.denominator)
 check(last-first<=2 and 0<=first<=last<=total,'complete unclipped maximum-three integer candidates')
 result={'contract':proof['contract'],'proof':copy.deepcopy(proof),'proof_sha256':digest(proof),'registered_quantity':q,'as_of':datetime.fromisoformat(as_of).astimezone(LOCAL).isoformat(),'quoted_per10':text,'one_last_digit_per10':pair(quantum),'quoted_ratio':pair(ratio),'exact_total_ratio':pair(exact),'exact_total_ratio_minus_quoted_ratio':pair(exact-ratio),'lower_ratio':pair(lower),'upper_ratio':pair(upper),'lower_entitlement':pair(lo),'upper_entitlement':pair(hi),'exact_total_ratio_entitlement':pair(q*exact),'possible_integer_shares':list(range(first,last+1)),'candidate_reason':'ALL_INTEGERS_FROM_FLOOR_LOWER_TO_CEIL_UPPER_ENTIRE_REGISTERED_ACCOUNT','rounding_scope':'ENTIRE_REGISTERED_ACCOUNT_NOT_FIFO_LOTS'}
 result.update({k:False for k in ('primary_document_bytes_verified_by_this_module','quoted_precision_is_certified','actual_registry_allocation_certified','probabilities_certified','globally_jointly_feasible','portfolio_return_ordering_claimed','account_replay_admitted')})
 return result

def chosen_quantity(event,component,q,audits,proofs,used):
 ratio=D(event['capital_per_share' if component=='capital' else 'stock_per_share']);nominal=ratio*q;key=(event['event_id'],component)
 if nominal==nominal.to_integral_value():check(key not in audits,'integer entitlement must not acquire registry override');return int(nominal)
 check(key in audits and component in proofs.get(event['event_id'],{}),'one proof/audit per noninteger component')
 row=audits[key];proof=proofs[event['event_id']][component];as_of=event['ex_date']+'T09:30:00+08:00';envelope=independent_bounds(proof,q,as_of)
 check(proof['event_id']==event['event_id'] and proof['issuer']==event['instrument'] and proof['record_date']==event['recorded'] and proof['ex_date']==event['ex_date'] and proof['component']==component and Fraction(proof['quoted_per10'])/10==Fraction(ratio),'original event/primary component ratio binding')
 check(set(row)==AUDIT_FIELDS and row['instrument']==event['instrument'] and row['recorded']==event['recorded'] and row['ex_date']==event['ex_date'] and type(row['registered_quantity']) is int and row['registered_quantity']==q and row['ratio_per_original_share']==str(ratio) and row['nominal_entitlement']==str(nominal) and row['as_of']==as_of and row['registry_proof_sha256']==envelope['proof_sha256'] and row['envelope']==envelope,'all primary allocation audit metadata independently reproduced')
 check(row['candidates']==envelope['possible_integer_shares'] and all(type(n) is int for n in row['candidates']) and type(row['chosen_integer_quantity']) is int and row['chosen_integer_quantity'] in row['candidates'],'chosen quantity in all independent Fraction candidates')
 check(key not in used,'duplicate component credit');used.add(key);return row['chosen_integer_quantity']

def closed_tree(nodes,proofs,events):
 """Rebuild every canonical child from independently bound source envelopes."""
 root=digest({});queue=[root];visited=set();leaves=[];branchpoints=[]
 while queue:
  node_id=queue.pop(0);check(node_id in nodes and node_id not in visited,'missing/repeated/cyclic uncertainty node');visited.add(node_id);node=nodes[node_id]
  check(node_id==digest(node['choices']) and node['portfolio_returns_computed'] is False and not node.get('persistence_errors'),'canonical unscored persisted path')
  no_ROI(node)
  if node['status']=='LOCAL_ALLOCATION_BRANCH_POINT':
   r=node['choice_request'];eid,component=r['event_id'],r['component'];check(eid in events and component in proofs.get(eid,{}) and component not in node['choices'].get(eid,{}),'unselected event-bound branch point')
   e=events[eid];check(r['instrument']==e['instrument'],'request source issuer');env=independent_bounds(proofs[eid][component],r['registered_quantity'],e['ex_date']+'T09:30:00+08:00');check(r['envelope']==env and r['candidates']==env['possible_integer_shares'],'all candidates/envelope independently Fraction reconstructed')
   children=[]
   for q in env['possible_integer_shares']:
    child=copy.deepcopy(node['choices']);child.setdefault(eid,{})[component]=q;identity=digest(child);check(identity in nodes and nodes[identity]['choices']==child,'every possible local allocation child exists');children.append(identity)
   check(node['child_node_ids']==children,'no omitted or selected uncertainty child');queue.extend(children);branchpoints.append(node_id)
  else:check(node['status']=='COMPLETE_RECONCILED_LEAF_UNSCORED','invalid account cannot count as complete leaf');leaves.append(node_id)
 check(visited==set(nodes),'orphan tree node or disconnected omitted path')
 return leaves,branchpoints

need=check
same=lambda a,b,message:check(D(str(a))==D(str(b)),message)
def fee_for(gross,action,cost):return cents(max(D(5),gross*D('0.0005' if action=='BUY' else '0.0015')))+cents(gross*D(cost)/10000)
def visible_risk(evidence,code,day,when):
 states=[s for s in evidence['state_intervals'] if s['instrument']==code and s['effective_from']<=day<=s['effective_through']]
 check(len(states)<=1,'nonoverlapping original issuer regime')
 return bool(states) and datetime.fromisoformat(states[0]['engineering_available_at'])<=datetime.fromisoformat(when)
def source_limits(evidence,code,day,row):
 reference=D(row['preclose']);check(reference.is_finite() and reference>0,'positive original opening reference')
 if row['isST']=='0':return reference*D('1.095'),reference*D('.905')
 check(row['isST']=='1' and visible_risk(evidence,code,day,clock(day,'09:25:00')),'supported original risk-warning source')
 epochs=[e for e in evidence['rule_epochs'] if e['valid_from']<=day<=e['valid_through']];check(len(epochs)==1,'one correct active rule epoch');epoch=epochs[0]
 check(datetime.fromisoformat(epoch['engineering_available_at'])<=datetime.fromisoformat(clock(day,'09:25:00')) and epoch['actual_arrival_verified'] is False,'rule available without actual arrival upgrade')
 ratio=D(epoch['limit_ratio']);check(ratio==(D('.05') if day<'2026-07-06' else D('.10')),'frozen July6 epoch boundary')
 upper=cents(reference*(1+ratio));lower=cents(reference*(1-ratio));return max(upper,reference+D('.01')),max(D('.01'),min(lower,reference-D('.01')))

def audit_physical(data,bps,events,sessions,targets,bars,evidence,proofs):
 days=data['days'];fills=data['fills'];orders=data['orders'];ledger=data['corporate_ledger'];ownership=data['ownership'];intents=data['intents']
 check([r['day'] for r in days]==sessions[:len(days)] and list(ownership)==[r['day'] for r in days],'complete continuous actual prefix')
 complete={r['day'] for r in days};check(all(f['execution_at'][:10] in complete for f in fills) and all(x['day'] in complete for x in ledger),'no ignored out-of-calendar fill or corporate row')
 records=defaultdict(list);exes=defaultdict(list)
 for e in events:records[e['recorded']].append(e);exes[e['ex_date']].append(e)
 following={sessions[i]:sessions[i+1] for i in range(len(sessions)-1)}
 ordermap={o['order_id']:o for o in orders};fillmap={f['order_id']:f for f in fills};check(len(ordermap)==len(orders) and len(fillmap)==len(fills),'unique observed orders/fills')
 byday=defaultdict(list)
 for o in orders:
     check(type(o['quantity']) is int and 0<o['quantity']<=1000000 and o['action'] in ('BUY','SELL'),'typed fixed physical order')
     check(o['eligible_at'] is not None and o['eligible_at']==clock(o['eligible_at'][:10],'09:30:00') and o['eligible_at'][:10] in sessions,'explicit source-session opening eligibility')
     byday[o['eligible_at'][:10]].append(o)
 byintent={i['execution_session']:i for i in intents};check(len(byintent)==len(intents),'unique fixed monthly intentions')
 expected_intents=[d for d in targets if targets[d]['as_of'] in complete];check(list(byintent)==expected_intents,'all priorclose fixed intentions, including cross-boundary order')
 allocation={}
 for row in data.get('registry_allocation_audit',[]):
     key=(row['event_id'],row['component']);check(key not in allocation,'duplicate allocation audit');allocation[key]=row
 used_allocations=set()
 cash=D('1000000');lots=defaultdict(list);claims=[];cashclaims=[];ent={};marks={};expectedledger=[];observedfills=[];nav={};exposure=[];peak=cash;dd=D(0);previous_equity=cash;maxvol=D(0);feesall=D(0);turnoverall=D(0);pendingdays=0;snapshotcount=0
 def circulation():return {c:sum(l['q'] for l in ls) for c,ls in lots.items() if ls}
 def owned():
     out=circulation()
     for cl in claims:
         if not cl['credited']:out[cl['instrument']]=out.get(cl['instrument'],0)+cl['quantity']
     return out
 for row in days:
     day=row['day'];daycorp=[];credit=D(0);fees=D(0)
     # Calendar availability is strictly after the published payment date.
     for cl in cashclaims:
         if not cl['paid'] and cl['available']==day:
             cash+=cl['net'];credit+=cl['net'];cl['paid']=True;daycorp.append({'day':day,'kind':'NET_DIVIDEND_CASH_AVAILABLE','event_id':cl['event_id'],'cash_delta':str(cl['net'])})
     for e in exes[day]:
         q=ent[e['event_id']];cap=chosen_quantity(e,'capital',q,allocation,proofs,used_allocations);stock=chosen_quantity(e,'stock',q,allocation,proofs,used_allocations)
         need(not(q and cap>0) or e['capital_tax_exempt_verified'] is True,'positive-owned capital tax guard')
         need(not(q and stock>0) or e['stock_tax_basis_verified'] is True,'bonus stock guard')
         gross=cents(D(e['cash_per_share'])*q);income=cents(D(e['stock_taxable_income_per_share'])*q);reserve=cents((gross+income)*D('.2'));need(reserve<=gross,'supported reserve')
         if gross:cashclaims.append({'event_id':e['event_id'],'net':gross-reserve,'available':next((d for d in sessions if d>e['pay_date']),None),'paid':False})
         for amount,kind in ((int(cap),'CAPITAL_TRANSFER'),(int(stock),'STOCK_DIVIDEND')):
             if amount:claims.append({'event_id':e['event_id'],'instrument':e['instrument'],'quantity':amount,'listed':e['listed'],'recorded':e['recorded'],'credited':False,'kind':kind})
         daycorp.append({'day':day,'kind':'EX_DATE_ENTITLEMENT','event_id':e['event_id'],'instrument':e['instrument'],'registered_quantity':q,'cash_gross':str(gross),'stress_tax_reserve':str(reserve),'capital_shares':int(cap),'stock_shares':int(stock),'taxable_stock_income':str(income)})
     for cl in claims:
         if not cl['credited'] and cl['listed']<=day:
             lots[cl['instrument']].append({'q':cl['quantity'],'day':cl['recorded'],'price':D(0)});cl['credited']=True
             daycorp.append({'day':day,'kind':'CAPITAL_SHARES_LISTED' if cl['kind']=='CAPITAL_TRANSFER' else 'STOCK_DIVIDEND_SHARES_LISTED','event_id':cl['event_id'],'quantity':cl['quantity']})
     dayorders=sorted(byday[day],key=lambda o:(o['action']!='SELL',o['security_id']))
     for o in dayorders:
         c=o['security_id'];action=o['action'];r=bars[c][day];need(r['date']==day and r['tradestatus'] in ('0','1'),'known exact current source state')
         risk=r['isST']=='1';upper,lower=source_limits(evidence,c,day,r)
         if risk:
             need(o['order_type']=='LIMIT' and o['trading_regime_contract']=='SSE_MAINBOARD_RISK_WARNING_HORIZON_V1' and D(o['limit_price'])==(upper if action=='BUY' else lower),'actual explicit risk-warning directional LIMIT')
             if action=='BUY' and evidence['account_capabilities']['risk_warning_buy_permission'] is False:
                 need(o['status']=='UNFILLED_RISK_WARNING_PERMISSION' and o['order_id'] not in fillmap,'unsigned STBUY terminal permission refusal');continue
         blocked=r['tradestatus']=='0' or action=='BUY' and D(r['open'])>=upper or action=='SELL' and D(r['open'])<=lower
         if blocked:need(o['status']=='UNFILLED_MARKET_CONSTRAINT' and o['order_id'] not in fillmap,'blocked order absent fill');continue
         p=D(r['open']);requested=o['quantity'];need(p.is_finite() and p>0 and p==cents(p),'positive cent-tick raw open')
         if risk:need(lower<=p<=upper,'risk warning actual open in selected epoch band')
         if action=='SELL':q=min(requested,sum(l['q'] for l in lots[c] if l['day']<day))
         else:
             q=min(requested,int((cash/p).to_integral_value(rounding=ROUND_DOWN))//100*100)
             while q>0 and p*q+fee_for(p*q,action,bps)>cash:q-=100
         if q<=0:
             need(o['status']=='UNFILLED_CASH_OR_T1' and o['order_id'] not in fillmap,'unaffordable/T1 order retained without fill');continue
         gross=p*q;cost=fee_for(gross,action,bps)
         need(o['order_id'] in fillmap,'nonblocked affordable order has observed fill');f=fillmap[o['order_id']]
         need(f['execution_at']==clock(day,'09:30:00') and f['security_id']==c and f['action']==action and type(f['quantity']) is int and f['quantity']==q and o['status']==('FILLED' if q==requested else 'PARTIAL_DAY_EXPIRED'),'fill/order exact physical quantity/time/status')
         same(f['price'],p,'exact source raw open fill');same(f['cost'],cost,'independent base+extra fees')
         if action=='BUY':need(q%100==0 and cash>=gross+cost,'100share buy affordability');cash-=gross+cost;lots[c].append({'q':q,'day':day,'price':p})
         else:
             cash+=gross-cost;remaining=q
             for l in lots[c]:
                 if l['day']>=day:continue
                 removed=min(remaining,l['q']);l['q']-=removed;remaining-=removed
             need(remaining==0,'FIFO removal complete');lots[c]=[l for l in lots[c] if l['q']]
         same(cash,f['cash_after'],'fill cash_after');need(cash>=0 and cash==cents(cash),'nonnegative cent cash');fees+=cost;feesall+=cost;turnoverall+=gross
         vol=D(r['volume']);need(vol>=q and vol>0,'whole-day necessary volume cap');maxvol=max(maxvol,D(q)/vol);observedfills.append(f)
     # Mark only with raw observations and documented suspension convention.
     for c,rows in bars.items():
         if day not in rows:continue
         r=rows[day]
         if r['isST']=='1' and not visible_risk(evidence,c,day,clock(day,'15:05:00')):continue
         if r['tradestatus']=='1':marks[c]=D(r['close'])
         elif any(e['instrument']==c for e in exes[day]):marks[c]=D(r['preclose'])
         elif c not in marks and r['close'] and D(r['close'])>0:marks[c]=D(r['close'])
     circ=circulation();own=owned()
     for c in own:
         need(c in bars and day in bars[c] and (bars[c][day]['isST']=='0' or visible_risk(evidence,c,day,clock(day,'09:25:00'))),'all actual held/pending source risk dependencies supported')
     need(circ==ownership[day],'circulating integer inventory')
     for e in records[day]:
         need(not any(not cl['credited'] and cl['instrument']==e['instrument'] for cl in claims),'no overlapping unlisted entitlement')
         q=circ.get(e['instrument'],0);ent[e['event_id']]=q;daycorp.append({'day':day,'kind':'RECORD_DATE_OWNERSHIP','event_id':e['event_id'],'instrument':e['instrument'],'quantity':q})
     market=sum((q*marks[c] for c,q in circ.items()),D(0));pending=sum((cl['quantity']*marks[cl['instrument']] for cl in claims if not cl['credited']),D(0));receivable=sum((cl['net'] for cl in cashclaims if not cl['paid']),D(0));equity=cash+market+pending+receivable
     if pending:pendingdays+=1
     expectedvalues={'cash':cash,'market_value':market,'pending_stock_value':pending,'cash_receivable':receivable,'equity':equity,'net_return':equity/previous_equity-1,'exposure':(market+pending)/equity,'fees':fees,'net_dividend_cash_available':credit}
     for k,v in expectedvalues.items():same(row[k],v,'daily '+str(bps)+' '+day+' '+k)
     nav[day]=equity;expectedledger.extend(daycorp);previous_equity=equity
     if day>='2024-01-02':exposure.append(expectedvalues['exposure']);peak=max(peak,equity);dd=min(dd,equity/peak-1)
     if day in following and following[day] in targets:
         exday=following[day];target=targets[exday];i=byintent[exday];asof=day+'T07:05:00+00:00';need(target['as_of']==day and i['as_of']==asof and i['owned_integer_shares']==own,'prior-close intent shares/clock');same(i['equity_at_decision'],equity,'intent continuous wealth')
         expecteddecisions=[]
         for c in sorted(set(own)|set(target['weights'])):
             held=own.get(c,0);w=D(str(target['weights'].get(c,0)))
             if not w:q=held;action='SELL'
             else:
                 need(bars[c][day]['tradestatus']=='1','prior-close target tradable')
                 desired=int((equity*w/marks[c]/100).to_integral_value(rounding=ROUND_DOWN))*100
                 if desired>held:q=(desired-held)//100*100;action='BUY'
                 else:q=held-desired;action='SELL'
             if q:expecteddecisions.append((action,c,q))
         expecteddecisions.sort(key=lambda d:(d[0]!='SELL',d[1]));need([(d['action'],d['security_id'],d['quantity']) for d in i['decisions']]==expecteddecisions,'actual target integer quantities')
         # Independently rebuild complete decision snapshot from reconstructed lots.
         positions={}
         for c,ls in lots.items():
             if not ls:continue
             q=sum(l['q'] for l in ls);positions[c]={'quantity':q,'average_price':str(sum((l['price']*l['q'] for l in ls),D(0))/q),'mark_price':str(marks[c]),'mark_source':'VISIBLE_PRICE'}
         wealth={'cash':cash,'positions':positions,'market_value':market,'cash_receivable':receivable,'pending_stock_value':pending,'equity':equity}
         record={'record_id':digest({'policy':'price_delay_d1','formation':day,'target':target}),'kind':'frozen_target','available_at':asof,'payload':target};visible=[record]
         for c in sorted(set(own)|set(target['weights'])):
             content={'instrument':c,'as_of':day,'known_mark':str(marks[c]),'source_bar':bars[c][day]};visible.append({'record_id':digest(content),'kind':'raw_market_state','available_at':asof,'payload':content})
         snap=digest({'as_of':asof,'records':visible,'account':clean(wealth)});need(i['snapshot_sha256']==snap,'complete reconstructed snapshot hash');snapshotcount+=1
         for d in i['decisions']:
             need(d['evidence_ids']==[record['record_id']] and d['reason']=='frozen monthly price_delay_d1 target, physical-share execution','decision evidence')
             did=digest({'decision':d,'snapshot':snap});expiry=exday+'T01:30:00+00:00';oid=digest({'decision_id':did,'at':asof,'expires_at':expiry});o=ordermap[oid]
             need(o['decision_id']==did and o['submitted_at']==asof and o['eligible_at']==o['expires_at']==expiry and (o['action'],o['security_id'],o['quantity'])==(d['action'],d['security_id'],d['quantity']),'decision/order complete identity')
 need(observedfills==fills,'all fills reconstructed in order')
 need(expectedledger==ledger,'all corporate ledger rows reconstructed exactly')
 need(len(ent)==sum(e['recorded'] in {r['day'] for r in days} for e in events) and Counter(x['kind'] for x in ledger)['EX_DATE_ENTITLEMENT']==sum(e['ex_date'] in {r['day'] for r in days} for e in events),'every due source record/ex event including zero quantities')
 need(set(allocation)==used_allocations,'all noninteger allocation audits consumed exactly once')
 check(len(observedfills)==len(fills) and len(expectedledger)==len(ledger),'every actual stream row consumed')
 return {'partial_or_complete_days':len(days),'intents':len(intents),'orders':len(orders),'fills':len(fills),'corporate_rows':len(ledger),'registry_allocations':len(allocation),'snapshot_hashes_reconstructed':snapshotcount,'final_cash_CNY':str(cash),'all_physical_cash_units_claims_T1_FIFO_fees_marks_equity_reconstructed':True,'fees_CNY':str(feesall),'gross_turnover_CNY':str(turnoverall),'max_whole_day_volume_fraction':str(maxvol)}, {'nav':nav,'exposure':exposure,'entitlements':ent,'circulation':circulation(),'cash':cash,'lots':dict(lots),'claims':cashclaims,'stock_claims':claims}

def load_leaf(folder):
 data={k:read(folder/(k+'.json')) for k in ('fills','orders','corporate_ledger','ownership','intents','registry_allocation_audit')}
 with (folder/'daily.csv').open(newline='') as stream:data['days']=list(csv.DictReader(stream))
 return data

def prefix_checks(base,data,folder,cost):
 for old,cut,count,intents in ((ORIGINAL,'2026-03-31',541,27),(STRICT,'2026-06-04',584,30)):
  part=read(base/old/str(cost)/'partial_case.json');state=read(base/old/str(cost)/'failed_account_state.json')
  check(len(part['rows'])==count and len(part['intents'])==intents and data['days'][:count]==part['rows'],'old failure daily prefix exact '+old)
  check([i for i in data['intents'] if i['execution_session']<cut]==part['intents'],'old failure monthly intent prefix exact '+old)
  check({d:v for d,v in data['ownership'].items() if d<cut}==part['ownership'],'old failure ownership prefix exact '+old)
  for key,field in (('fills','execution_at'),('corporate_ledger','day')):check([v for v in data[key] if v[field][:10]<cut]==state[key],'old failure financial stream prefix exact '+old+' '+key)
 oldfolder=base/OLDDAY/str(cost);oldsummary=read(base/OLDDAY/'summary.json');checkpoint=read(folder/'pre2026_checkpoint.json');oldhash=oldsummary['results_by_extra_bps'][str(cost)]['artifact_sha256'];days=[r for r in data['days'] if r['day']<=PRE]
 with (oldfolder/'daily.csv').open(newline='') as stream:check(list(csv.DictReader(stream))==days and len(days)==486,'old486 CSV row prefix')
 stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(days[0]));writer.writeheader();writer.writerows(days);hashes={'daily.csv':hashlib.sha256(stream.getvalue().encode()).hexdigest()}
 objs={k:checkpoint[k] for k in ('orders','fills','corporate_ledger')};objs['intents']=[i for i in data['intents'] if i['execution_session']<=PRE];objs['ownership']={d:v for d,v in data['ownership'].items() if d<=PRE}
 check(len(objs['intents'])==24,'old24 intent prefix')
 for k,v in objs.items():
  check(read(oldfolder/(k+'.json'))==v,'old original object prefix '+k);hashes[k+'.json']=hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest()
 check(hashes==oldhash,'old six serialized financial hashes exact')
 scope=read(folder/'source_scope_audit.json');oldscope=read(base/'price-delay-ordinary-source-scope-20261021/scope.json')['nonordinary_source_intervals']
 expected=[{'instrument':r['instrument'],'session':r['day'],'reason':'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT','original_row_present':True,'source_isST':'1','required_by_account':False,'synthetic_price_created':False} for r in oldscope]
 check(len(expected)==241 and [r for r in scope if r['session']<=PRE]==expected,'old241 scope evidence exact')
 return {'old486_24_six_financial_bytes_exact':True,'old541_27_failure_prefix_exact':True,'strict584_30_failure_prefix_exact':True,'old241_scope_prefix_exact':True,'reconstructed_pre2026_financial_sha256':hashes}

def phase_checks(folder,data,sessions,bars,evidence,events):
 phases=read(folder/'phase_audit.json');regimes=read(folder/'regime_audit.json');check(len(phases)==len(regimes)==4*len(sessions),'four actual phase and regime records per explicit session')
 ent={r['event_id']:r['quantity'] for r in data['corporate_ledger'] if r['kind']=='RECORD_DATE_OWNERSHIP'};prev={};heldst=0;storders=[];executions=0
 allowed={'date','code','preclose','tradestatus','isST','adjustflag','open'}
 for index,day in enumerate(sessions):
  pp=phases[4*index:4*index+4];rr=regimes[4*index:4*index+4]
  check([(r['session'],r['phase'],r['as_of']) for r in pp]==[(day,p,clock(day,t)) for p,t in [('PREOPEN_SOURCE_VALIDATED','09:25:00'),('OPEN_VALIDATED_BEFORE_ACCOUNT_START','09:30:00'),('OPEN_EXECUTED','09:30:00'),('CLOSE_RECORDED','15:05:00')]],'source/open/validation/start/close phase clock')
  check([(r['session'],r['phase']) for r in rr]==[(day,p) for p in ('PREOPEN','OPEN_VALIDATION','OPEN','CLOSE')],'regime phase order')
  def no_future_fields(obj):
   if isinstance(obj,dict):
    check(not ({'open','high','low','close','volume','amount'}&set(obj)),'PREOPEN carries no opening/full-day quote');[no_future_fields(v) for v in obj.values()]
   elif isinstance(obj,list):[no_future_fields(v) for v in obj]
  no_future_fields(rr[0])
  required=set(prev)|{o['security_id'] for o in data['orders'] if o['eligible_at']==clock(day,'09:30:00')}|{e['instrument'] for e in events if e['ex_date']==day and ent.get(e['event_id'],0)}
  # Pending shares are included in prior ownership for this source set: listing is same-day for every actual positive entitlement.
  check(required<=set(pp[0]['required']),'preopen actual ownership/order/positive entitlement dependencies')
  for c in pp[3]['required']:
   check(day in bars[c] and (bars[c][day]['isST']=='0' or visible_risk(evidence,c,day,clock(day,'15:05:00'))),'all CLOSE target/owned dependencies supported without source exclusion')
  for phase in (rr[1],rr[2]):
   for row in phase['execution']:
    check(set(row['quote'])<=allowed and row['quote']=={k:v for k,v in bars[row['instrument']][day].items() if k in allowed},'OPEN quote uses only current opening field whitelist')
    check(row['validate_only'] is (phase is rr[1]),'complete opening batch validation precedes actual account execution');executions+=1
  prev=data['ownership'][day]
  heldst+=sum(bars[c][day]['isST']=='1' for c in prev)
 for order in data['orders']:
  day=order['eligible_at'][:10];src=bars[order['security_id']][day]
  if src['isST']!='1':continue
  up,down=source_limits(evidence,order['security_id'],day,src)
  check(order['order_type']=='LIMIT' and D(order['limit_price'])==(up if order['action']=='BUY' else down),'explicit actual ST limit metadata')
  if order['action']=='BUY':check(order['status']=='UNFILLED_RISK_WARNING_PERMISSION' and not any(f['order_id']==order['order_id'] for f in data['fills']),'ST permission false refuses entire request')
  storders.append({'session':day,'instrument':order['security_id'],'action':order['action'],'status':order['status'],'quantity':order['quantity'],'limit_price':order['limit_price'],'rule_limit_ratio':'0.05' if day<'2026-07-06' else '0.10'})
 expected_scope=[]
 for day in sessions:
  for c,rows in sorted(bars.items()):
   if day in rows and rows[day]['isST']=='1' and not visible_risk(evidence,c,day,clock(day,'09:25:00')):expected_scope.append({'instrument':c,'session':day,'reason':'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT','original_row_present':True,'source_isST':'1','required_by_account':False,'synthetic_price_created':False})
 check(read(folder/'source_scope_audit.json')==expected_scope,'all current unused nonordinary source exceptions independently reconstructed')
 return {'all_source_scope_rows_reconstructed':len(expected_scope),'all676_phase_sequences_verified':True,'opening_field_whitelist_verified':True,'opening_execution_records':executions,'held_ST_issuer_days':heldst,'actual_ST_orders':storders,'ST_BUY_fills':0}

def metrics(nav):
 a,b,end=nav['2024-12-31'],nav[PRE],nav[END];ys=[(a/D(1000000)-1)*100,(b/a-1)*100,(end/b-1)*100]
 return {'2024_return_pct':float(ys[0]),'2025_return_pct':float(ys[1]),'2026_through_2026-10-20_return_pct':float(ys[2]),'2026_starting_equity':str(b),'ending_equity':str(end),'three_numeric_conditions_met_at_interim_cutoff':ys[0]>0 and ys[1]>0 and ys[2]>=10}
def compare_metrics(actual,expected):
 check(set(actual)==set(expected),'exact annual metric schema')
 for k,v in expected.items():
  if k.endswith('_pct'):check(isclose(actual[k],v,rel_tol=1e-12,abs_tol=1e-12),'independent continuous annual denominator '+k)
  else:check(actual[k]==v,'independent annual metric '+k)
def negative(fn):
 try:fn()
 except (AssertionError,KeyError,ValueError):return True
 raise AssertionError('semantic negative unexpectedly accepted')

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for n in ('source-root','repo-root','plan','expected-plan-sha256','freeze-commit','output'):parser.add_argument('--'+n,required=True)
 parser.add_argument('--terminal-confirmed',action='store_true');args=parser.parse_args();check(args.terminal_confirmed,'root actual terminal confirmation required')
 base,repo,out=map(lambda s:Path(s).resolve(),(args.source_root,args.repo_root,args.output));root=base/RUN;planpath=Path(args.plan).resolve();check(not out.exists() and not out.is_relative_to(base) and not out.is_relative_to(repo),'new external audit report only')
 check(sha(planpath)==args.expected_plan_sha256,'external frozen request SHA');plan=read(planpath);summary=read(root/'summary.json');known=read(root/'input-before.json');post=read(root/'input-postcheck.json')
 check(summary['status']=='COMPLETE_LOCAL_REGISTRY_ENVELOPE_DIAGNOSTIC' and summary['plan_sha256']==args.expected_plan_sha256,'actual complete diagnostic status and external plan')
 check(plan['extra_cost_bps']==[20,40] and plan['allocator']=='plan_integer_targets' and plan['initial_CNY']=='1000000' and plan['candidate']=='price_delay_d1' and plan['source_queries']==0 and plan['investment_rule_changed'] is False,'original fixed method and two complete cost trees')
 for n,h in known.items():check(sha(n)==h,'all bound actual before/after bytes '+n)
 for field in ('method_code_sha256','public_evidence_sha256'):
  for n,h in plan[field].items():
   check(sha(repo/n)==h==known[str((repo/n).resolve())],'request actual binding '+n)
   check(hashlib.sha256(subprocess.check_output(['git','show',args.freeze_commit+':'+n],cwd=repo)).hexdigest()==h,'pushed freeze blob '+n)
 check(hashlib.sha256(subprocess.check_output(['git','show',args.freeze_commit+':'+str(planpath.relative_to(repo))],cwd=repo)).hexdigest()==args.expected_plan_sha256,'frozen request Git blob')
 check(post=={'all_bound_inputs_unchanged':True,'source_authentication_repeated':True,'errors':[],'completed':True} and summary['source_postcheck']==post,'complete repeated postcheck before score')
 for f in ('all_local_candidates_globally_jointly_feasible_certified','probabilities_certified','actual_registry_allocation_certified','strict_failed_accounts_relabelled_success','full_October_2026_complete','sealed_2026_evidence_claimed','historical_arrival_verified','queue_and_impact_calibrated','actual_FIFO_tax_liability_verified','objective_achieved'):check(summary[f] is False,'retained evidence boundary '+f)
 check(summary['execution_error'] is None and summary['scoring_error'] is None and summary['annual_returns_computed_after_all_trees_complete'] is True,'both trees complete and postchecked before all metrics')
 strictaudit=read(repo/'experiments/qlib/price-delay-regime-horizon-failure-independent-audit.json');check(strictaudit['summary_sha256']==sha(base/STRICT/'summary.json') and strictaudit['imports_project_code'] is False,'strict failure independently audited anchor')
 preserved={**strictaudit['old60_financial_sha256'],**strictaudit['old10_failure_artifact_sha256']}
 for n,h in strictaudit['all_output_file_sha256'].items():preserved[STRICT+'/'+n]=h
 check(len(preserved)==83,'all old60 plus10 originalfailure plus13 strictfailure')
 for n,h in preserved.items():check(sha(base/n)==h==known[str((base/n).resolve())],'original complete/failed evidence immutable '+n)
 proofs=read(repo/PROOFS)
 for components in proofs.values():
  for proof in components.values():check(any(Path(n).name==proof['source_file'] and h==proof['source_sha256'] for n,h in known.items()),'bound primary original SHA for envelope proof')
 evidence=read(repo/EVIDENCE);events=read(base/SOURCE/'derived_events.json');eventmap={e['event_id']:e for e in events};check(len(events)==len(eventmap)==613,'original613 independently admitted events')
 eventaudit=read(repo/'experiments/qlib/price-delay-horizon-event-source-independent-audit.json');check(eventaudit['events_reconstructed']==613 and eventaudit['summary_sha256']==sha(base/SOURCE/'summary.json') and not eventaudit['critical_or_important_findings'],'independent source613 anchor')
 rm=read(base/RAW/'manifest.json');sessions=read(base/RAW/'calendar.json')['sessions'];check(len(sessions)==676 and sessions[0]==START and sessions[-1]==END and sessions[:486]==read(base/OLDRAW/'calendar.json')['sessions'],'676 explicit original calendar including486 prefix')
 oldcodes=set(read(base/OLDRAW/'manifest.json')['per_code_sha256']);targets=read(base/'price-delay-horizon-formations-20261021/candidate_targets.json');check(len(targets)==34,'frozen34 target continuation');first=min(d for d in targets if d>PRE);boundary=set(targets[first]['weights'])-oldcodes;bars={}
 for code,h in rm['per_code_sha256'].items():
  path=base/RAW/'codes'/(code+'.json');check(sha(path)==h,'actual203 raw packet binding');packet=read(path);rows=packet['bars'];check([r['date'] for r in rows]==sessions,'complete676 source rows')
  if code in oldcodes:check([r for r in rows if r['date']<=PRE]==read(base/OLDRAW/'codes'/(code+'.json'))['bars'],'old151 literal raw prefix')
  bars[code]={r['date']:r if code in oldcodes or r['date']>PRE else {k:v for k,v in r.items() if k in {'date','code','close','tradestatus','isST'}} for r in rows if code in oldcodes or r['date']>PRE or code in boundary and r['date']==PRE}
 check(len(bars)==203 and len(oldcodes)==151,'fixed203 includingold151 source visibility')
 outputs_before={str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()};profiles={};allraw={};allnodes={};sample=None
 # Authenticate and reconstruct ALL nodes of BOTH trees before calculating any annual metric.
 for cost in (20,40):
  nodes=read(root/str(cost)/'nodes.json');leaves,branchpoints=closed_tree(nodes,proofs,eventmap);allnodes[str(cost)]={'nodes':len(nodes),'leaves':len(leaves),'branchpoints':len(branchpoints),'closed_all_candidates':True}
  check(summary['trees'][str(cost)]['complete'] is True and summary['trees'][str(cost)]['nodes']==len(nodes) and summary['trees'][str(cost)]['leaf_count']==len(leaves),'summary complete tree counts')
  profiles[str(cost)]={};allraw[str(cost)]={}
  for node_id,node in nodes.items():
   folder=root/str(cost)/node_id;check(read(folder/'result.json')==node and read(folder/'choices.json')==node['choices'],'all canonical node/result/choice persistence')
   if node_id in branchpoints:
    check({p.name for p in folder.iterdir()}=={'result.json','choices.json','partial_trace.json','account_state.json'},'exact four branchpoint artifacts');part=read(folder/'partial_trace.json');state=read(folder/'account_state.json');request=node['choice_request'];e=eventmap[request['event_id']]
    data={'days':part['rows'],'intents':part['intents'],'ownership':part['ownership'],**{k:state[k] for k in ('fills','orders','corporate_ledger','registry_allocation_audit')}}
    result,rebuilt=audit_physical(data,cost,events,sessions,targets,bars,evidence,proofs)
    check(state['last_account_clock']==[part['rows'][-1]['day'],1] and e['ex_date']==part['day'] and state['entitlements'][e['event_id']]==request['registered_quantity']==rebuilt['entitlements'][e['event_id']],'branchpoint pre-mutation clock/source registered quantity')
    check(all(r['day']<e['ex_date'] for r in state['corporate_ledger']) and all(f['execution_at'][:10]<e['ex_date'] for f in state['fills']) and D(state['cash'])==rebuilt['cash'],'no branchpoint failing-day account mutation')
    continue
   check({p.name:sha(p) for p in folder.iterdir() if p.name!='result.json'}==node['artifact_sha256'],'complete exact leaf artifact SHA map')
   data=load_leaf(folder);check(len(data['days'])==676 and len(data['intents'])==34,'all676 continuousdays/34 fixed intentions')
   result,rebuilt=audit_physical(data,cost,events,sessions,targets,bars,evidence,proofs);result['prefix_checks']=prefix_checks(base,data,folder,cost);result['phase_and_ST_checks']=phase_checks(folder,data,sessions,bars,evidence,events)
   profiles[str(cost)][node_id]=result;allraw[str(cost)][node_id]=rebuilt
   if sample is None:sample=(data,cost,nodes,node_id)
 # Full hash recheck before reporting independently calculated return values.
 for n,h in known.items():check(sha(n)==h,'all frozen inputs unchanged after reconstruction')
 check({str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}==outputs_before,'all observed output bytes unchanged during independent audit')
 independent={}
 for cost in ('20','40'):
  independent[cost]={node:metrics(raw['nav']) for node,raw in allraw[cost].items()};actual=summary['results_by_extra_bps'][cost]
  check(set(actual['leaf_results'])==set(independent[cost]) and actual['complete_leaf_count']==len(independent[cost]),'all closed leaves scored with no selection')
  for node,m in independent[cost].items():compare_metrics(actual['leaf_results'][node],m)
  for k,v in actual['annual_return_ranges_pct'].items():check(all(isclose(x,y,rel_tol=1e-12,abs_tol=1e-12) for x,y in zip(v,[min(m[k] for m in independent[cost].values()),max(m[k] for m in independent[cost].values())])),'allleaf return range')
  check(actual['all_leaves_meet_three_interim_numeric_conditions']==all(m['three_numeric_conditions_met_at_interim_cutoff'] for m in independent[cost].values()),'allleaf exact numeric gate')
 data,cost,nodes,nodeid=sample;neg={}
 changed=copy.deepcopy(nodes);rootid=digest({});del changed[changed[rootid]['child_node_ids'][0]];neg['missing_allocation_candidate_rejected']=negative(lambda:closed_tree(changed,proofs,eventmap))
 for field,mutator in [('fee',lambda d:d['fills'][0].__setitem__('cost',str(D(d['fills'][0]['cost'])+D('.01')))),('allocation',lambda d:d['registry_allocation_audit'][0].__setitem__('chosen_integer_quantity',999)),('corporate_listing_time',lambda d:next(r for r in d['corporate_ledger'] if r['kind']=='CAPITAL_SHARES_LISTED').__setitem__('day',sessions[-1]))]:
  changed=copy.deepcopy(data);mutator(changed);neg[field+'_tamper_rejected']=negative(lambda:audit_physical(changed,cost,events,sessions,targets,bars,evidence,proofs))
 changed=copy.deepcopy(bars);f=data['fills'][0];changed[f['security_id']][f['execution_at'][:10]]['open']=str(D(f['price'])+D('.01'));neg['raw_open_not_equal_fill_rejected']=negative(lambda:audit_physical(data,cost,events,sessions,targets,changed,evidence,proofs))
 changed=copy.deepcopy(bars);changed[f['security_id']][f['execution_at'][:10]]['tradestatus']='0';neg['halted_source_fill_rejected']=negative(lambda:audit_physical(data,cost,events,sessions,targets,changed,evidence,proofs))
 report={'status':'PASS_INDEPENDENT_COMPLETE_LOCAL_REGISTRY_ENVELOPE_AUDIT','summary_sha256':sha(root/'summary.json'),'plan_sha256':args.expected_plan_sha256,'freeze_commit':subprocess.check_output(['git','rev-parse',args.freeze_commit],cwd=repo,text=True).strip(),'audit_code_sha256':sha(__file__),'imports_project_code':False,'account_or_production_reconciler_or_scorer_called':False,'all_cost_trees_closed_before_independent_annual_metrics':True,'trees':allnodes,'all_four_leaf_676day_physical_ledgers_reconstructed':True,'profiles':profiles,'independent_continuous_annual_metrics':independent,'all_bound_input_sha256':known,'all_output_file_sha256':outputs_before,'original83_complete_and_failed_file_sha256':preserved,'semantic_negative_controls_rejected':neg,'strict_failure_preserved':True,'all_three_old_financial_and_scope_prefixes_preserved':True,'source_or_target_modified':False,'network_or_new_source_queries':False,'all_local_candidates_globally_jointly_feasible_certified':False,'actual_registry_allocation_certified':False,'probabilities_certified':False,'full_October_2026_complete':False,'sealed_2026_evidence_claimed':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['DAILY_PROXY source-open execution; full-day volume is only an after-close necessary capacity check. Not minute liquidity, queue or impact calibration.','All conservative local display-precision envelope candidates are included. Actual registry allocation, joint global feasibility, probabilities, tax liability and historical source arrival are not certified.','Strict failed accounts and source objects remain unchanged. This diagnostic does not retroactively admit the strict fractional entitlement.','Interim horizon ends October20; full October and sealed forward performance are not certified. All four 2026 interim returns are negative and numeric objective is unmet.']}
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps({'status':report['status'],'output':str(out),'audit_code_sha256':sha(__file__),'report_sha256':sha(out),'trees':allnodes}))
if __name__=='__main__':main()
