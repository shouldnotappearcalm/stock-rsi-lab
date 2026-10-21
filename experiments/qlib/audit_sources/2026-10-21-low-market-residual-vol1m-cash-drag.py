"""Read-only pre2026 exposure attribution, no simulation or portfolio-return calculation.
Independent binary decoding; no project imports. All monetary figures CNY;
normalized quantities remain Qlib proxy quantities, not certified raw shares.
"""
from pathlib import Path
from collections import defaultdict, Counter
import csv, hashlib, json, math, struct
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
O=B/'low-market-residual-vol1m-pre2026-development-20261021'
P=B/'qlib-price-delay-pre2026-clock-v2-20261021'
F=O/'40/low_market_residual_vol_1m'
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
DEST=Path('/tmp/low-market-residual-vol1m-pre2026-cash-drag-attribution-20261021.json')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_bytes())
def rows(p):
 with p.open() as h:return list(csv.DictReader(h))
def same(a,b):assert math.isclose(a,b,rel_tol=1e-9,abs_tol=2e-5),(a,b)
def stats(a):return {'mean':math.fsum(a)/len(a),'min':min(a),'max':max(a)}
def amountstats(a):return {'count':len(a),'prior_close_notional_CNY':math.fsum(x['prior_close_notional_CNY'] for x in a),'execution_open_notional_CNY':math.fsum(x['execution_open_notional_CNY'] or 0 for x in a),'missing_execution_open_count':sum(x['execution_open_notional_CNY'] is None for x in a)}
summary=load(O/'summary.json');s=summary['results_by_extra_bps_and_family']['40/low_market_residual_vol_1m']
planpath=R/'experiments/qlib/low-market-residual-vol1m-pre2026-development-plan.json';plan=load(planpath)
assert sha(planpath)==summary['plan_sha256'];assert summary['2026_market_values_queried'] is False
artifacts={n:sha(F/n) for n in s['artifact_sha256']};assert artifacts==s['artifact_sha256']
manifest=load(P/'manifest.json');assert sha(P/'manifest.json')==plan['provider_manifest_sha256'];assert manifest['all_output_values_at_or_before']=='2025-12-31'
calendar=(P/'calendars/day.txt').read_text().splitlines();assert calendar[-1]=='2025-12-31';assert sha(P/'calendars/day.txt')==plan['input_sha256']['calendars/day.txt'];index={d:i for i,d in enumerate(calendar)}
binaries={};sources={};read_dates=[]
def value(code,field,day):
 assert day<='2025-12-31' and day in index
 key=(code,field)
 if key not in binaries:
  rel=f'features/{code.lower()}/{field}.day.bin';raw=(P/rel).read_bytes();h=hashlib.sha256(raw).hexdigest();assert h==manifest['per_feature'][rel]['sha256'];sources[rel]=h
  a=struct.unpack('<'+'f'*(len(raw)//4),raw);assert a[0]==int(a[0]);off=int(a[0]);assert off+len(a)-2<len(calendar);binaries[key]=(off,a[1:])
 off,a=binaries[key];j=index[day]-off;read_dates.append(day);v=a[j] if 0<=j<len(a) else float('nan');return v if math.isfinite(v) and v>0 else None
intents=load(F/'decision_intents.json');days=rows(F/'days.csv');orders=rows(F/'orders.csv');holdings=rows(F/'holdings.csv')
assert len(intents)==24 and len(days)==485;assert len({i['execution_session'] for i in intents})==24
D={r['session']:r for r in days};H=defaultdict(dict);Q=defaultdict(dict)
for h in holdings:H[h['session']][h['instrument']]=h
for o in orders:assert o['instrument'] not in Q[o['session']];Q[o['session']][o['instrument']]=o
assert len(orders)==s['orders'];unfilled=[];monthly=[];partial=[]
for i in intents:
 day=i['execution_session'];prior=i['as_of_close_convention'][:10];assert prior==calendar[index[day]-1] and prior<day;assert i['execution_exchange_queried_for_decision'] is False
 E=float(i['equity_at_decision']);held=i['holdings_at_decision'];weights=i['target_weights'];same(math.fsum(weights.values()),.95)
 if prior in D:
  same(E,float(D[prior]['account_value']));assert set(held)==set(H[prior])
  for c,q in held.items():same(q,float(H[prior][c]['normalized_units']))
 else:assert E==1000000 and not held
 closes={c:value(c,'close',prior) for c in set(held)|set(weights)};assert all(closes.values())
 floorunits={};lotloss=[]
 for c,w in weights.items():
  p,f=closes[c],value(c,'factor',prior);assert f
  physical=math.floor(E*w/p*f/100+1e-10)*100;floorunits[c]=physical/f
  lotloss.append({'instrument':c,'weight':w,'known_normalized_close':p,'known_factor':f,'ideal_notional_CNY':E*w,'floor_target_physical_shares_proxy':physical,'floor_target_normalized_units':physical/f,'floor_notional_CNY':physical/f*p,'floor_shortfall_CNY':E*w-physical/f*p})
 expectedpost=dict(held);seen=set();priorcash=E-math.fsum(q*closes[c] for c,q in held.items());cash=priorcash;postfill=dict(held)
 for a in i['orders']:
  c=a['instrument'];assert c not in seen;seen.add(c);side=a['side'];sign=1 if side=='BUY' else -1;q=float(a['normalized_units']);assert q>0
  expectedpost[c]=expectedpost.get(c,0)+sign*q
  o=Q[day][c];assert o['side']==side;same(abs(float(o['requested_normalized_units'])),q)
  actualq=abs(float(o['filled_normalized_units']));px=value(c,'open',day);f=value(c,'factor',day);priorp=closes[c]
  postfill[c]=postfill.get(c,0)+sign*actualq
  roundshares=math.floor((q*f+.1)/100)*100 if f else None
  gap=px/priorp-1 if px else None
  limit=gap is not None and (gap>=.095 if side=='BUY' else gap<=-.095)
  full_exit=a['quantity_basis']=='KNOWN_INVENTORY_FULL_EXIT'
  # Qlib uses np.isclose(rtol=1e-5,atol=1e-8) to bypass SELL rounding for full liquidation.
  equivalent_to_all_held=abs(q-held.get(c,0))<=1e-8+1e-5*abs(held.get(c,0))
  fee_rate=.0045 if side=='BUY' else .0055
  required=q*px+max(5,q*px*fee_rate) if px else None
  record={'execution_session':day,'formation_asof':prior,'instrument':c,'side':side,'quantity_basis':a['quantity_basis'],'requested_normalized_units':q,'requested_physical_shares_execution_factor_proxy':q*f if f else None,'execution_factor':f,'execution_lot_rounded_shares_proxy':roundshares,'full_exit_intent':full_exit,'execution_rounding_bypassed_if_sell_all':side=='SELL' and equivalent_to_all_held,'prior_close_notional_CNY':q*priorp,'execution_open_notional_CNY':q*px if px else None,'execution_open_vs_prior_close_change':gap,'frozen_directional_open_limit_hit':limit,'cash_before_order_observed_fill_bridge_CNY':cash,'requested_buy_cash_including_fees_CNY':required if side=='BUY' else None}
  if o['fill_status']=='UNFILLED':
   assert actualq==float(o['signed_trade_value'])==float(o['cost'])==0
   if px is None:category='MISSING_EXECUTION_OPEN_OR_SUSPENDED_SOURCE'
   elif limit:category='FROZEN_DIRECTIONAL_OPEN_LIMIT'
   elif roundshares==0 and not (side=='SELL' and equivalent_to_all_held):category='EXECUTION_LOT_ROUNDING_TO_ZERO'
   elif side=='BUY' and cash<max(q*px*fee_rate,5):category='OBSERVED_CASH_CANNOT_COVER_REQUEST_FEE'
   elif side=='BUY' and required>cash:category='OBSERVED_CASH_LIMIT_CANDIDATE_UNRESOLVED_EXACT_CAUSE'
   else:category='UNRESOLVED_FROM_RETAINED_EVIDENCE'
   record['evidence_category']=category;unfilled.append(record)
  elif abs(actualq-q)>1e-8:
   record.update(filled_normalized_units=actualq,unexecuted_normalized_units=q-actualq,unexecuted_prior_close_notional_CNY=(q-actualq)*priorp,unexecuted_execution_open_notional_CNY=(q-actualq)*px if px else None)
   partial.append(record)
  cash-=float(o['signed_trade_value'])+float(o['cost'])
 assert seen==set(Q[day]);same(cash,float(D[day]['cash']))
 for c,q in postfill.items():same(q,float(H[day].get(c,{}).get('normalized_units',0)))
 ideal=.95*E;floorN=math.fsum(q*closes[c] for c,q in floorunits.items());plannedN=math.fsum(q*closes[c] for c,q in expectedpost.items());actualPriorN=math.fsum(q*closes[c] for c,q in postfill.items())
 assert floorN<=ideal+1e-6;assert plannedN<=floorN+1e-5
 fees=float(D[day]['cost']);execution_exposure=100*float(D[day]['stock_value'])/float(D[day]['account_value'])
 later=[d for d in days if d['session'][:7]==day[:7]]
 monthly.append({'execution_session':day,'formation_asof':prior,'equity_at_decision_CNY':E,'target_names':len(weights),'ideal_target_exposure_pct':95.,'target_floor_notional_CNY':floorN,'target_floor_exposure_pct':100*floorN/E,'target_floor_gap_CNY':ideal-floorN,'target_floor_gap_pp':100*(ideal-floorN)/E,'intended_post_order_prior_close_notional_CNY':plannedN,'intended_post_order_prior_close_exposure_pct':100*plannedN/E,'additional_buy_delta_lot_floor_gap_CNY':floorN-plannedN,'additional_buy_delta_lot_floor_gap_pp':100*(floorN-plannedN)/E,'actual_postfill_at_prior_close_notional_CNY':actualPriorN,'actual_postfill_at_prior_close_exposure_pct':100*actualPriorN/E,'all_nonexecution_net_long_notional_shortfall_at_prior_close_CNY':plannedN-actualPriorN,'all_nonexecution_net_long_exposure_shortfall_at_prior_close_pp':100*(plannedN-actualPriorN)/E,'execution_day_close_exposure_pct':execution_exposure,'execution_valuation_and_NAV_denominator_bridge_pp':100*actualPriorN/E-execution_exposure,'execution_day_fees_CNY':fees,'unfilled_orders':sum(o['fill_status']=='UNFILLED' for o in Q[day].values()),'observed_calendar_month_daily_mean_exposure_pct':math.fsum(100*float(d['stock_value'])/float(d['account_value']) for d in later)/len(later),'calendar_month_daily_observations':len(later),'target_lot_details':lotloss})
for m in monthly:same(95-m['target_floor_gap_pp']-m['additional_buy_delta_lot_floor_gap_pp']-m['all_nonexecution_net_long_exposure_shortfall_at_prior_close_pp']-m['execution_valuation_and_NAV_denominator_bridge_pp'],m['execution_day_close_exposure_pct'])
assert len(unfilled)==253;assert Counter(x['side'] for x in unfilled)=={'SELL':192,'BUY':61}
by=defaultdict(list);by_day=defaultdict(list)
for u in unfilled:
 by[u['side']+'/'+u['evidence_category']].append(u)
 by_day[u['execution_session']+'/'+u['side']+'/'+u['evidence_category']].append(u)
exp=[100*float(d['stock_value'])/float(d['account_value']) for d in days];same(math.fsum(exp)/485,s['average_exposure_pct'])
fields=['target_floor_exposure_pct','target_floor_gap_pp','intended_post_order_prior_close_exposure_pct','additional_buy_delta_lot_floor_gap_pp','actual_postfill_at_prior_close_exposure_pct','all_nonexecution_net_long_exposure_shortfall_at_prior_close_pp','execution_day_close_exposure_pct','execution_valuation_and_NAV_denominator_bridge_pp']
# Re-express each monthly snapshot component with its observed month-session weight;
# remaining difference is within-month exposure drift, not an inferred return effect.
weighted=lambda k:math.fsum(m[k]*m['calendar_month_daily_observations'] for m in monthly)/485
weightedbridge={'baseline_target_pct':95,'target_floor_gap_pp':weighted('target_floor_gap_pp'),'additional_buy_delta_lot_floor_gap_pp':weighted('additional_buy_delta_lot_floor_gap_pp'),'net_nonexecution_gap_pp':weighted('all_nonexecution_net_long_exposure_shortfall_at_prior_close_pp'),'execution_valuation_and_NAV_bridge_pp':weighted('execution_valuation_and_NAV_denominator_bridge_pp'),'within_month_observed_exposure_drift_pp':weighted('execution_day_close_exposure_pct')-math.fsum(exp)/485,'observed_daily_mean_exposure_pct':math.fsum(exp)/485}
same(weightedbridge['baseline_target_pct']-math.fsum(v for k,v in weightedbridge.items() if k not in ('baseline_target_pct','observed_daily_mean_exposure_pct')),weightedbridge['observed_daily_mean_exposure_pct'])
for n,h in artifacts.items():assert sha(F/n)==h
for n,h in sources.items():assert sha(P/n)==h
report={'status':'PRE2026_READ_ONLY_CASH_EXPOSURE_ATTRIBUTION_COMPLETE','profile':'40/low_market_residual_vol_1m','summary_sha256':sha(O/'summary.json'),'plan_sha256':sha(planpath),'provider_manifest_sha256':sha(P/'manifest.json'),'financial_artifact_sha256':artifacts,'audit_code_sha256':sha(Path(__file__)),'imports_project_code':False,'account_replay_rerun':False,'portfolio_returns_computed':False,'2026_quotes_or_results_read':False,'network_used':False,'repository_modified':False,'intents':24,'daily_observations':485,'observed_daily_exposure_pct':stats(exp),'monthly_snapshot_statistics':{k:stats([m[k] for m in monthly]) for k in fields},'day_weighted_descriptive_bridge_95pct_to_observed_mean':weightedbridge,'unfilled_orders':253,'interpretation':{'candidate_remains_rejected_under_original_90pct_gate':True,'mean_exposure_shortfall_to_90pct_gate_pp':90-math.fsum(exp)/485,'unfilled_sell_orders_are_not_lost_buy_exposure':True,'all_cash_drag_attributed_to_rounding':False,'reason':'Measured lot truncation and open-limit rejection both contribute; the major concentration is57 frozen limit-hit BUY orders on2024-10-08. Valuation/NAV and within-month drift remain separate arithmetic bridge terms.'},'unfilled_by_side_and_evidence':{k:amountstats(v) for k,v in sorted(by.items())},'unfilled_by_day_side_and_evidence':{k:amountstats(v) for k,v in sorted(by_day.items())},'unfilled_details':unfilled,'filled_or_partial_quantity_differences':{'count':len(partial),'by_side':{side:amountstats([x for x in partial if x['side']==side]) for side in ('BUY','SELL')},'signed_prior_close_net_long_shortfall_CNY':math.fsum((1 if x['side']=='BUY' else -1)*x['unexecuted_prior_close_notional_CNY'] for x in partial),'details':partial},'monthly_prior_close_floor_exposure':monthly,'source_feature_sha256':sources,'source_quote_read_dates':{'minimum':min(read_dates),'maximum':max(read_dates)},'evidence_boundaries':['DAILY_OPEN_NORMALIZED_QLIB_PROXY only; physical-share counts are factor translations, not raw-share execution certification.','First target lot floor and second incremental BUY lot floor are distinct measured stages.','UNFILLED SELL orders retain stock and can increase exposure; their notional must not be counted as lost BUY exposure.','Execution rejection classifications are evidence categories reconstructed from frozen source and observed cash, not broker rejection-reason logs.','Nominal unfilled amounts are repeated rebalance intentions, not additive persistent idle cash or a performance-loss estimate.','Daily mean exposure is descriptive. Day-weighted snapshot bridge is an arithmetic decomposition; valuation/NAV-denominator change and within-month drift are retained separately.','No allocation proposal or new alpha, counterfactual strategy, portfolio returns, or2026data were computed.']}
DEST.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'report':str(DEST),'sha256':sha(DEST),'script_sha256':report['audit_code_sha256'],'monthly_stats':report['monthly_snapshot_statistics'],'weightedbridge':weightedbridge,'unfilled_categories':report['unfilled_by_side_and_evidence']},indent=2))
