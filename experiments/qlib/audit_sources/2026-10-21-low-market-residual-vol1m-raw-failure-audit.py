"""Independent stdlib physical-state audit of a preserved failed pre2026 run.
No project imports, simulator, annual scorer, portfolio returns or network.
"""
from pathlib import Path
from decimal import Decimal as D, ROUND_HALF_UP
from collections import defaultdict,Counter
import argparse,copy,hashlib,json,subprocess
RAW='low-market-residual-vol1m-raw-pre2026-20261021';SOURCE='low-market-residual-vol1m-account-source-events-pre2026-20261021';DEV='low-market-residual-vol1m-budgeted-pre2026-development-20261021';RUN='low-market-residual-vol1m-raw-development-pre2026-20261021'
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
def audit_profile(base,root,bps,events,sessions,targets,bars):
 folder=root/str(bps);state=read(folder/'failed_account_state.json');trace=read(folder/'partial_engine_trace.json');deps=read(folder/'required_source_dependencies.json');error=read(folder/'error.json')
 check(error['status']=='INVALID_ACCOUNT_OR_SOURCE' and error['error_type']=='ValueError' and error['annual_returns_computed'] is False,'preserved ordinary guard failure')
 failed=trace['failed_session'];check(failed=='2025-12-16' and state['last_account_clock']==['2025-12-15',1],'failure before day start mutation')
 complete_days=sessions[:sessions.index(failed)];check([r['day'] for r in trace['days']]==complete_days and len(complete_days)==474,'474continuous complete partial days')
 check(len(trace['intents'])==24 and [i['execution_session'] for i in trace['intents']]==list(targets),'24 retained fixed intentions')
 byevent={e['event_id']:e for e in events};fd=defaultdict(list);cd=defaultdict(list)
 for f in state['fills']:check(f['execution_at'][:10]<failed,'no failing/later fills');fd[f['execution_at'][:10]].append(f)
 for c in state['corporate_ledger']:check(c['day']<failed,'no failing/later corporate mutation');cd[c['day']].append(c)
 cash=D('1000000');lots={};cashclaims=[];stockclaims=[];entitlements={};daily_owned={};marks={};record_quantities={};fees_total=D(0);signed_total=D(0);cashcredits=D(0)
 for row in trace['days']:
  day=row['day'];beforecash=cash;netcash=D(0);dayfee=D(0)
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
   src=bars(c)[day];price=D(f['price']);check(src['isST']=='0' and src['tradestatus']=='1' and price==D(src['open']),'ordinary actual open source')
   reference=D(src['preclose']);check(price<reference*D('1.095') if buy else price>reference*D('.905'),'frozen directional reference limits')
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
  listed=qmap(lots);check(trace['ownership'][day]==listed,'every partial daily listed ownership')
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
  market=sum((n*marks[c] for c,n in listed.items()),D(0));pendingvalue=sum((n*marks[c] for c,n in pending.items()),D(0));receivable=sum((D(x['net']) for x in cashclaims if not x['paid']),D(0))
  check(cash==D(row['cash']) and market==D(row['market_value']) and pendingvalue==D(row['pending_stock_value']) and receivable==D(row['cash_receivable']),'every partial daily cash and asset component')
  check(cash+market+pendingvalue+receivable==D(row['equity']),'every partial daily equity conservation')
  check(dayfee==D(row['fees']) and netcash==D(row['net_dividend_cash_available']),'every daily fee/cash credit')
 check(cash==D(state['cash'])==D('1000000')-signed_total-fees_total+cashcredits,'initial1m aggregate cash conservation')
 same_lots(lots,state['positions']);same_claims(cashclaims,state['cash_claims']);same_claims(stockclaims,state['stock_claims']);check(entitlements==state['entitlements'],'all retained entitlements')
 check(daily_owned[complete_days[-1]]==state['owned_shares'],'final owned shares including pending claims')
 unknown=[]
 for e in events:
  key=e['instrument']+'|'+e['ex_date']
  if key not in UNKNOWN:continue
  rr=[r for r in state['corporate_ledger'] if r['event_id']==e['event_id'] and r['kind']=='RECORD_DATE_OWNERSHIP'];xx=[r for r in state['corporate_ledger'] if r['event_id']==e['event_id'] and r['kind']=='EX_DATE_ENTITLEMENT'];check(len(rr)==len(xx)==1 and rr[0]['quantity']==xx[0]['registered_quantity']==0,'six unknown actual zero record and EX ownership')
  unknown.append({'event_key':key,'event_id':e['event_id'],'record_quantity':0,'ex_registered_quantity':0,'tax_verification_granted':False})
 check(len(unknown)==6,'six unknown events retained')
 for intent in trace['intents']:
  execution=intent['execution_session'];asof=intent['as_of'][:10];check(asof==sessions[sessions.index(execution)-1]==targets[execution]['as_of'],'priorclose next-session intent')
  check(intent['owned_integer_shares']==daily_owned[asof],'intent actual owned integer inventory');check(D(intent['equity_at_decision'])==D(next(x['equity'] for x in trace['days'] if x['day']==asof)),'priorclose account equity')
  receipt=intent['allocation_receipt'];check(receipt['execution_prices_or_returns_used'] is False and receipt['future_cash_or_fill_guaranteed'] is False and receipt['physical_integer_orders'] is True,'budgeted receipt boundaries')
  check(D(str(receipt['final_planned_notional']))<=D(str(receipt['target_notional_budget']))+D('.0001'),'allocation fixed notional budget')
  post=dict(intent['owned_integer_shares'])
  for d in intent['decisions']:
   check(type(d['quantity']) is int and d['quantity']>0 and (d['action']!='BUY' or d['quantity']%100==0),'physical decisions lots');c=d['security_id'];post[c]=post.get(c,0)+d['quantity']*(1 if d['action']=='BUY' else -1)
  for c,n in receipt['post_order_normalized_positions'].items():check(D(str(n))==post.get(c,0),'budgeted receipt matches emitted physical decisions')
 reasons={c:[] for c in trace['required_codes']}
 for c,n in state['owned_shares'].items():
  if n:reasons.setdefault(c,[]).append('OWNED_PHYSICAL_OR_PENDING_STOCK')
 for o in state['orders']:
  if o['status']=='PENDING':reasons.setdefault(o['security_id'],[]).append('PENDING_ORDER')
 for e in events:
  if e['ex_date']==failed and state['entitlements'].get(e['event_id'],0):reasons.setdefault(e['instrument'],[]).append('POSITIVE_EX_ENTITLEMENT')
 following=sessions[sessions.index(failed)+1];target=targets.get(following)
 for c in (target or {}).get('weights',{}):reasons.setdefault(c,[]).append('NEXT_TARGET_PRIOR_CLOSE')
 check(trace['following_session']==following and trace['following_target']==target and deps['dependency_reasons']==reasons,'failure required dependency reasons')
 check(set(trace['required_codes'])=={c for c,v in reasons.items() if v},'failure dependency completeness')
 for c,r in deps['source_rows'].items():check(r==bars(c).get(failed),'every failed dependency row is literal current source')
 check(deps['source_rows_synthesized'] is False and deps['failed_guard_bypassed'] is False,'guard not bypassed')
 check(state['owned_shares']['SH600079']==900 and 'SH600079' in trace['required_codes'] and bars('SH600079')[failed]['isST']=='1','actual mandatory owned900shares sourceST')
 check('required nonordinary source state: SH600079 2025-12-16' in error['error'],'exact source guard trigger')
 return {'status':'FAILED_ADMISSION_CORRECTLY_PRESERVED','failed_session':failed,'last_account_clock':state['last_account_clock'],'all474_partial_daily_ledgers_reconstructed':True,'partial_daily_rows':474,'monthly_intents':24,'fills_verified':len(state['fills']),'orders_preserved':len(state['orders']),'corporate_ledger_records_reconstructed':len(state['corporate_ledger']),'cash_reconstructed_CNY':str(cash),'signed_fill_notional_CNY':str(signed_total),'fill_costs_CNY':str(fees_total),'net_cash_distribution_credits_CNY':str(cashcredits),'owned_SH600079_shares':900,'source_SH600079_isST':'1','failure_before_start_day_credit_or_fill':True,'actual_six_unknown_zero_ownership':unknown,'annual_ROI_recomputed':False}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('source-root','repo-root','plan','expected-plan-sha256','freeze-commit','output'):p.add_argument('--'+n,required=True)
 p.add_argument('--terminal-confirmed',action='store_true');a=p.parse_args();check(a.terminal_confirmed,'terminal confirmation required')
 base,repo,out=map(lambda s:Path(s).resolve(),(a.source_root,a.repo_root,a.output));root=base/RUN;check(not out.exists() and not out.is_relative_to(base) and not out.is_relative_to(repo),'new external audit output')
 planpath=Path(a.plan).resolve();check(sha(planpath)==a.expected_plan_sha256,'external frozen raw plan');plan=read(planpath);known=read(root/'input-before.json');summary=read(root/'summary.json');post=read(root/'input-postcheck.json')
 check(summary['plan_sha256']==a.expected_plan_sha256 and summary['method_code_sha256']==plan['method_code_sha256'],'summary plan/method bindings')
 for name,h in {**plan['method_code_sha256'],plan['protocol_file']:plan['protocol_sha256']}.items():check(sha(repo/name)==h==hashlib.sha256(subprocess.check_output(['git','show',a.freeze_commit+':'+name],cwd=repo)).hexdigest(),'frozen code/protocol '+name)
 rel=str(planpath.relative_to(repo));check(hashlib.sha256(subprocess.check_output(['git','show',a.freeze_commit+':'+rel],cwd=repo)).hexdigest()==a.expected_plan_sha256,'frozen plan blob')
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for n,h in plan[field].items():check(sha(parent/n)==h and known[str((parent/n).resolve())]==h,'actual frozen raw input '+n)
 for name,h in known.items():check(sha(name)==h,'all actual before/after immutable bytes')
 check(post=={'source_inputs_unchanged_after_replay':True} and summary['postcheck_sha256']==sha(root/'input-postcheck.json'),'actual successful input postcheck')
 check(summary['status']=='IVOL_RAW_PRE2026_FAILED_OR_INCOMPLETE_PRESERVED' and summary['annual_returns_computed'] is False and summary['both_profiles_complete_before_annual_scoring'] is False and summary['raw_daily_proxy_development_gate_passes'] is False,'failed status/annual scorer gate')
 for f in ('2026_return_computed','new_2026_queries','candidate_promoted','objective_achieved','minute_execution_admitted','actual_FIFO_tax_liability_verified'):check(summary[f] is False,'no promotion/2026 boundary')
 check(set(summary['results_by_extra_bps'])=={'20','40'} and read(root/'case_results.json')==summary['results_by_extra_bps'],'both profiles preserved')
 sa=read(repo/SOURCE_AUDIT);check(sa['status']=='PASS_INDEPENDENT_PRE2026_EVENT_SOURCE_AUDIT' and sa['all862_events_independently_reconstructed'] is True and sa['imports_project_code'] is False,'independent source audit prerequisite')
 for name,h in sa['source_artifact_sha256'].items():check(sha(base/SOURCE/name)==h,'actual audited source artifact unchanged')
 financial=sa['old42_financial_sha256'];check(len(financial)==42,'42old financial artifacts')
 for n,h in financial.items():check(sha(base/DEV/n)==h==known[str((base/DEV/n).resolve())],'old42 actual audited financial bytes unchanged')
 events=read(base/SOURCE/'derived_events.json');check(len(events)==862,'862frozen source events');targets=read(base/DEV/'targets.json')['low_market_residual_vol_1m'];sessions=read(base/RAW/'calendar.json')['sessions'];check(len(sessions)==486 and sessions[-1]=='2025-12-31','pre2026 calendar')
 manifest=read(base/RAW/'manifest.json');cache={}
 def bars(c):
  if c not in cache:
   f=base/RAW/'codes'/(c+'.json');check(sha(f)==manifest['per_code_sha256'][c],'immutable raw packet');packet=read(f);check(packet['window']==['2023-12-29','2025-12-31'],'only pre2026 raw accepted source');cache[c]={r['date']:r for r in packet['bars']};check(all(d<='2025-12-31' for d in cache[c]),'no2026source quotes')
  return cache[c]
 results={}
 for b in (20,40):
  r=summary['results_by_extra_bps'][str(b)];check(r['status']=='INVALID_ACCOUNT_OR_SOURCE' and r['annual_returns_computed'] is False,'failed profile cannot expose annual ROI')
  check(not any('return_pct' in n or n in ('average_exposure_pct','max_drawdown_pct') for n in r),'no invalid-profile aggregate performance score')
  files={x.name:sha(x) for x in (root/str(b)).iterdir() if x.is_file()};check(files==r['failure_artifact_sha256'],'all failure artifact hashes')
  check(read(root/str(b)/'error.json')=={k:v for k,v in r.items() if k!='failure_artifact_sha256'},'failure error summary linkage');results[str(b)]=audit_profile(base,root,b,events,sessions,targets,bars)
 output_hashes={str(f.relative_to(root)):sha(f) for f in sorted(root.rglob('*')) if f.is_file()}
 for name,h in known.items():check(sha(name)==h,'all immutable inputs unchanged after independent audit')
 report={'status':'PASS_INDEPENDENT_FAILED_RAW_ACCOUNT_PRESERVATION_AUDIT','verdict':'FAILED_ORDINARY_SOURCE_ADMISSION_CORRECTLY_PRESERVED_NOT_STRATEGY_SUCCESS','summary_sha256':sha(root/'summary.json'),'plan_sha256':a.expected_plan_sha256,'freeze_commit':subprocess.check_output(['git','rev-parse',a.freeze_commit],cwd=repo,text=True).strip(),'audit_code_sha256':sha(__file__),'results_by_extra_bps':results,'all_output_file_sha256':output_hashes,'all_bound_inputs_actual_sha256':known,'old42_financial_sha256':financial,'source_summary_sha256':sa['source_summary_sha256'],'source_audit_sha256':sha(repo/SOURCE_AUDIT),'imports_project_code':False,'account_replay_rerun':False,'annual_scorer_called':False,'portfolio_returns_computed_by_audit':False,'2026_source_or_results_read':False,'network_used':False,'production_or_source_modified':False,'guard_bypassed':False,'critical_or_important_findings':[],'objective_achieved':False,'limitations':['This is a partial failed DAILY_PROXY account diagnostic, not a complete2024/25 performance test or minute/PIT acceptance.','All474partial-day cash/units/assets and source/corporate accounting are independently reconstructed; no annual ROI or factor attribution is computed.','Six unresolved tax events remain unknown with independently verified actual zero record/ex quantities in this partial run.','Failure sourceisST1with900actual ownedSH600079shares is preserved at2025-12-16 before start_day; no ticker/target/guard change.']}
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(out),'sha256':sha(out),'code_sha256':report['audit_code_sha256'],'profiles':{k:{n:v for n,v in x.items() if n in ('failed_session','cash_reconstructed_CNY','owned_SH600079_shares','partial_daily_rows')} for k,x in results.items()}}))
if __name__=='__main__':main()
