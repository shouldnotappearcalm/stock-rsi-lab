"""Independent stdlib CSV audit. No production imports, pickle loading or replay.
Reads only a physically pre2026 provider; Jan2026 metadata is never a quote.
"""
from pathlib import Path
from collections import defaultdict
import argparse, csv, hashlib, json, math, struct, subprocess

REPO=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
OUT=BASE/'low-market-residual-vol1m-budgeted-pre2026-development-20261021'
PROVIDER=BASE/'qlib-price-delay-pre2026-clock-v2-20261021'
PLAN=None
REPORT=None
EXPECTED=None
FREEZE=None
GAPS=None

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def csvrows(p):
    with p.open() as f:return list(csv.DictReader(f))
def check(v,label):
    if not v:raise AssertionError(label)
def same(a,b,label,absolute=2e-5):
    check(math.isfinite(float(a)) and math.isfinite(float(b)) and math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=absolute),f'{label}: {a} != {b}')

def equivalent(actual, expected):
    if isinstance(expected, dict):
        assert set(actual)==set(expected), (set(actual),set(expected))
        for key in expected:equivalent(actual[key],expected[key])
    elif isinstance(expected, (list,tuple)):
        assert len(actual)==len(expected)
        for a,b in zip(actual,expected):equivalent(a,b)
    elif isinstance(expected,bool) or expected is None or isinstance(expected,str):
        assert actual==expected and type(actual)==type(expected)
    else:same(actual,expected,'independent allocation numeric')


def independent_allocation(equity, held, weights, asof, source_value):
    budget=equity*math.fsum(weights.values());q={};quotes={};desired={};options=[]
    for c in sorted(c for c,w in weights.items() if w>0):
        p=source_value(c,'close',asof);f=source_value(c,'factor',asof)
        assert p is not None and p>0 and f is not None and f>0
        lot=100/f;lot_value=100*p/f;v=equity*weights[c];current=held.get(c,0.)
        desired[c]=v;quotes[c]=(p,f,lot)
        if current*p<=v:
            count=math.floor((v-current*p)/lot_value+1e-10)
            q[c]=current+count*lot
        else:q[c]=math.floor(v/lot_value+1e-10)*lot
        trial=q[c]+lot;action='ONE_BUY_LOT'
        if current*p>v:
            trial=min(trial,current)
            action='CANCEL_REMAINING_SELL' if trial==current else 'REDUCE_SELL_ONE_LOT'
        expense=(trial-q[c])*p
        gap=v-q[c]*p
        improvement=gap**2-(v-trial*p)**2
        if expense>0 and improvement>0:
            options.append((float(format(improvement,'.12g')),c,trial,expense,improvement,action))
    initial=math.fsum(q[c]*quotes[c][0] for c in q)
    before=math.fsum((desired[c]-q[c]*quotes[c][0])**2 for c in q)
    remaining=budget-initial;steps=[]
    for _,c,trial,expense,improvement,action in sorted(options,key=lambda r:(-r[0],r[1])):
        if expense<=remaining+max(1e-8,equity*1e-10):
            steps.append({'instrument':c,'normalized_units_added':trial-q[c],
                'notional_added':expense,'squared_error_reduction':improvement,'action':action})
            q[c]=trial;remaining-=expense
    orders=[]
    for c,current in held.items():
        if current>0 and weights.get(c,0.)==0:
            orders.append({'instrument':c,'side':'SELL','normalized_units':current,
                'known_normalized_close':None,'known_factor':None,'as_of':asof,
                'quantity_basis':'KNOWN_INVENTORY_FULL_EXIT'})
    for c in sorted(q):
        current=held.get(c,0.);change=q[c]-current;p,f,lot=quotes[c]
        if abs(change)<=1e-8*max(1.,current,q[c]):continue
        if change>0:assert math.isclose(change*f/100,round(change*f/100),rel_tol=1e-10,abs_tol=1e-8)
        orders.append({'instrument':c,'side':'BUY' if change>0 else 'SELL',
            'normalized_units':abs(change),'known_normalized_close':p,'known_factor':f,
            'as_of':asof,'quantity_basis':'PRIOR_CLOSE_BUDGETED_LOT_TARGET'})
    final=math.fsum(q[c]*quotes[c][0] for c in q)
    after=math.fsum((desired[c]-q[c]*quotes[c][0])**2 for c in q)
    assert final<=budget+max(1e-8,equity*1e-10) and after<=before+max(1e-8,before*1e-10)
    receipt={'as_of':asof,'target_notional_budget':budget,'initial_planned_notional':initial,
        'final_planned_notional':final,'unallocated_notional_budget':budget-final,
        'squared_tracking_error_before':before,'squared_tracking_error_after':after,
        'post_order_normalized_positions':q,'allocation_steps':steps,
        'execution_prices_or_returns_used':False,'future_cash_or_fill_guaranteed':False}
    return sorted(orders,key=lambda o:(o['side']!='SELL',o['instrument'])),receipt


BASELINE_EVIDENCE_FILES={
'experiments/qlib/low-market-residual-vol1m-pre2026-development-plan.json',
'experiments/qlib/low-market-residual-vol1m-pre2026-development-results.json',
'experiments/qlib/low-market-residual-vol1m-pre2026-development-independent-audit.json',
'experiments/qlib/low-market-residual-vol1m-pre2026-cash-drag-attribution.json'}


def verify_baseline(plan):
    check(set(plan['baseline_evidence_sha256'])==BASELINE_EVIDENCE_FILES,'exact baseline evidence set')
    for n,h in plan['baseline_evidence_sha256'].items():check(digest(REPO/n)==h,'baseline evidence '+n)
    old=BASE/'low-market-residual-vol1m-pre2026-development-20261021'
    audit=read(REPO/'experiments/qlib/low-market-residual-vol1m-pre2026-development-independent-audit.json')
    check(audit['summary_sha256']==plan['baseline_summary_sha256']==digest(old/'summary.json'),'canonical old summary')
    check(audit['plan_sha256']==plan['baseline_evidence_sha256']['experiments/qlib/low-market-residual-vol1m-pre2026-development-plan.json'],'canonical old plan')
    summary=read(old/'summary.json');actual={f'{label}/{n}':h for label,case in summary['results_by_extra_bps_and_family'].items() for n,h in case['artifact_sha256'].items()}
    check(actual==audit['financial_artifact_hashes_verified'] and len(actual)==42,'42 canonical financial artifacts')
    for n,h in actual.items():check(digest(old/n)==h,'old artifact '+n)
    check(digest(old/'targets.json')==plan['initial_targets_sha256'] and digest(old/'formation_receipts.json')==plan['initial_receipts_sha256'],'unchanged alpha target/receipts')
    return actual


def main():
    plan=read(PLAN); summary=read(OUT/'summary.json');baseline_hashes=verify_baseline(plan)
    check(digest(PLAN)==EXPECTED==summary['plan_sha256'],'external plan')
    freeze=subprocess.check_output(['git','rev-parse',FREEZE],cwd=REPO,text=True).strip()
    check(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(PLAN.relative_to(REPO))],cwd=REPO)).hexdigest()==EXPECTED,'freeze plan')
    check(summary['method_code_sha256']==plan['method_code_sha256'],'summary methods')
    for n,h in plan['method_code_sha256'].items():
        check(digest(REPO/n)==h,'current method '+n)
        check(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=REPO)).hexdigest()==h,'frozen method '+n)
    check(plan['families']==['low_market_residual_vol_1m'] and set(plan['descriptive_controls'])=={'low_total_vol_1m_control','eligible_equal_weight'} and plan['candidate_budget']==1,'single selectable candidate')
    check(plan['status']=='FROZEN_LOW_MARKET_RESIDUAL_VOL1M_BUDGETED_BEFORE_OUTCOMES' and plan['capital_CNY']==1000000 and plan['extra_bps']==[20,40] and plan['reference_extra_bps']==40 and plan['window']==['2024-01-02','2025-12-31'],'fixed account protocol')
    check(summary['status']=='LOW_MARKET_RESIDUAL_VOL1M_BUDGETED_PRE2026_DEVELOPMENT_COMPLETE','terminal complete summary')
    check(digest(REPO/'docs/research/low-market-residual-vol1m-budgeted-design-2026-10-21.md')==plan['design_sha256'],'design')
    check(digest(REPO/plan['formation_independent_audit_file'])==plan['formation_independent_audit_sha256'],'formation independent audit')
    check(digest(BASE/'low-market-residual-vol1m-pre2026-formations-20261021/summary.json')==plan['formation_summary_sha256'],'formation summary')
    manifest=read(PROVIDER/'manifest.json');check(digest(PROVIDER/'manifest.json')==plan['provider_manifest_sha256'],'provider manifest')
    check(len(manifest['per_feature'])==4010,'4010 physical feature files')
    for n,m in manifest['per_feature'].items():
        check(digest(PROVIDER/n)==m['sha256'] and m['last_date']<='2025-12-31','physical feature identity '+n)
    check(digest(PROVIDER/'calendars/day_future.txt')==plan['future_calendar_sha256'],'clock metadata hash')
    check(digest(PROVIDER/'features/sh000905/close.day.bin')==plan['market_close_sha256'],'market source')
    for n,h in plan['input_sha256'].items():
        if n!='price_files':check(digest(PROVIDER/n)==h,'source input '+n)
    codes=set()
    for row in (PROVIDER/'instruments/csi500.txt').read_text().splitlines():
        c,a,b=row.split()
        if c.startswith(('SH600','SH601','SH603','SH605','SZ000','SZ001','SZ002','SZ003')) and a<='2025-12-31' and b>='2023-12-29':codes.add(c)
    paths=['instruments/all.txt']+[f'features/{c.lower()}/{f}.day.bin' for c in sorted(codes) for f in ('open','high','low','close','volume','factor','amount','adjclose')]+['features/sh000905/adjclose.day.bin']
    aggregate=hashlib.sha256()
    for n in paths:aggregate.update(n.encode()+b'\0'+(PROVIDER/n).read_bytes()+b'\0')
    check(aggregate.hexdigest()==plan['input_sha256']['price_files'],'aggregate price input')
    gapmanifest=read(GAPS/'manifest.json');check(digest(GAPS/'manifest.json')==plan['gap_state_manifest_sha256'],'gap capture manifest')
    check(gapmanifest['status']=='PRE2026_INDEPENDENT_GAP_STATE_CAPTURE' and gapmanifest['2026_market_values_queried'] is False and gapmanifest['window']==['2023-12-29','2025-12-31'],'gap source boundary')
    states={}
    for c,h in gapmanifest['per_code_sha256'].items():
        p=GAPS/'codes'/(c+'.json');check(digest(p)==h,'gap packet '+c);packet=read(p)
        check(packet['instrument']==c,'gap issuer');rows=packet['rows'];dates=[x['date'] for x in rows]
        check(dates==sorted(set(dates)) and all('2023-12-29'<=d<='2025-12-31' for d in dates),'gap dates')
        states[c]={x['date']:x for x in rows}

    check(manifest['all_output_values_at_or_before']=='2025-12-31','pre2026 provider')
    calendar=(PROVIDER/'calendars/day.txt').read_text().splitlines()
    check(calendar==sorted(set(calendar)) and calendar[-1]=='2025-12-31' and digest(PROVIDER/'calendars/day.txt')==plan['input_sha256']['calendars/day.txt'],'calendar')
    sessions=[d for d in calendar if '2024-01-02'<=d<='2025-12-31'];check(len(sessions)==485,'485')
    check((PROVIDER/'calendars/day_future.txt').read_text().splitlines()==calendar+[plan['clock_only_next_session']] and plan['clock_only_next_session']=='2026-01-05','clock-only boundary')
    previous={calendar[i]:calendar[i-1] for i in range(1,len(calendar))};index={d:i for i,d in enumerate(calendar)}
    monthly=[]
    for d in sessions:
        if not monthly or monthly[-1][:7]!=d[:7]:monthly.append(d)
    check(len(monthly)==24,'monthly clock')
    targets=read(OUT/'targets.json');receipts=read(OUT/'formation_receipts.json')
    check(digest(OUT/'targets.json')==summary['targets_sha256']==plan['initial_targets_sha256'],'targets')
    check(digest(OUT/'formation_receipts.json')==summary['formation_receipts_sha256']==plan['initial_receipts_sha256'],'receipts')
    check(set(targets)=={'low_market_residual_vol_1m','low_total_vol_1m_control','eligible_equal_weight'},'target families')
    for f,t in targets.items():
        check(list(t)==monthly,'24 targets '+f)
        for d,v in t.items():check(v['as_of']==previous[d],'target prior '+f)
    check([r['execution_session'] for r in receipts]==monthly,'receipt clock')
    for r in receipts:
        check(r['formation_asof']==previous[r['execution_session']] and r['latest_factor_price_read']==r['formation_asof'] and r['controls_selectable'] is False,'receipt asof')
        month=r['formation_asof'][:7];sample=[d for d in calendar if d[:7]==month]
        check(r['return_month']==month and r['sample_dates']==r['return_dates']==sample and r['baseline_close_day']==previous[sample[0]] and r['close_dates']==[previous[sample[0]]]+sample and r['n']==len(sample)>=15,'receipt complete prior month')

    binaries={};source_hashes={}
    def value(code,field,day,carry=False):
        check(day<='2025-12-31','no2026 quote read')
        key=(code,field)
        if key not in binaries:
            rel=f'features/{code.lower()}/{field}.day.bin';p=PROVIDER/rel;raw=p.read_bytes()
            check(digest(p)==manifest['per_feature'][rel]['sha256'],'feature hash '+rel)
            check(len(raw)%4==0,'float32 bytes');v=struct.unpack('<'+'f'*(len(raw)//4),raw);offset=int(v[0]);check(offset+len(v)-2<len(calendar),'no future binary values')
            binaries[key]=(offset,v[1:]);source_hashes[rel]=manifest['per_feature'][rel]['sha256']
        off,vals=binaries[key];i=index[day]-off
        while 0<=i<len(vals):
            p=vals[i]
            if math.isfinite(p) and p>0:return p
            if not carry:return None
            i-=1
        return None
    labels={f'{c}/{f}' for c in (20,40) for f in targets};check(set(summary['results_by_extra_bps_and_family'])==labels,'6 cases')
    results={};hashes={}
    for label in sorted(labels):
        cost,family=label.split('/');cost=int(cost);folder=OUT/label;s=summary['results_by_extra_bps_and_family'][label]
        names={'days.csv','orders.csv','holdings.csv','decision_intents.json','suspension_mark_audit.json','report.pkl','positions.pkl'}
        check(set(s['artifact_sha256'])==names,'7 artifact scope')
        for n,h in s['artifact_sha256'].items():check(digest(folder/n)==h,'artifact '+label+'/'+n);hashes[label+'/'+n]=h
        days=csvrows(folder/'days.csv');orders=csvrows(folder/'orders.csv');holdings=csvrows(folder/'holdings.csv');intents=read(folder/'decision_intents.json');marks=read(folder/'suspension_mark_audit.json')
        check([d['session'] for d in days]==sessions,'continuous sessions '+label)
        od=defaultdict(list);hd=defaultdict(dict)
        for o in orders:
            check(o['session'] in sessions,'order day');check(o['instrument'] not in {x['instrument'] for x in od[o['session']]},'unique session/instrument order');od[o['session']].append(o)
        for h in holdings:check(h['session'] in sessions and h['instrument'] not in hd[h['session']],'unique holding');hd[h['session']][h['instrument']]=h
        cash=1000000.;units=defaultdict(float);totalcost=turnover=0.;unfilled=0;nav={'2023-12-29':1000000.};exposure=[];high=1000000.;drawdown=0.;gaps=[];rounding_overshoots=[]
        for d in days:
            day=d['session'];prior=previous[day];check(d['signal_date']==prior and d['signal_bar_close_convention']==prior+'T15:00:00+08:00','daily priorclose')
            check((d['signal_present']=='True')==(prior in {v['as_of'] for v in targets[family].values()}),'signal presence')
            fee=tv=signed=0.
            for o in od[day]:
                check(o['signal_date']==prior and prior in {v['as_of'] for v in targets[family].values()},'order signal')
                side=o['side'];check(side in ('BUY','SELL'),'side');sign=1 if side=='BUY' else -1
                q=float(o['filled_normalized_units']);amount=float(o['requested_normalized_units']);gross=float(o['signed_trade_value']);c=float(o['cost'])
                check(math.isfinite(q) and math.isfinite(amount) and sign*q>=0 and sign*amount>=0,'signed units');check(abs(q)<=abs(amount)+.10001/value(o['instrument'],'factor',day),'filled vs requested rounding allowance')
                if abs(q)>abs(amount)+1e-8:rounding_overshoots.append({'session':day,'instrument':o['instrument'],'excess_normalized_units':abs(q)-abs(amount),'excess_physical_shares':(abs(q)-abs(amount))*value(o['instrument'],'factor',day)})
                check(sign*gross>=0 and c>=0,'signed gross/cost')
                if o['fill_status']=='UNFILLED':
                    check(q==gross==c==0,'unfilled cash');unfilled+=1
                else:
                    check(o['fill_status']=='FILLED_OR_PARTIAL' and sign*q>0,'fill status');price=float(o['normalized_price']);same(q*price,gross,'gross identity');check(cash>=-1e-4,'nonnegative previous cash')
                    same(price,value(o['instrument'],'open',day),'open source')
                    rate=(.0005 if sign==1 else .0015)+cost/10000;same(max(5,abs(gross)*rate),c,'fee rule')
                units[o['instrument']]+=q;fee+=c;tv+=abs(gross);signed+=gross
            cash-=signed+fee;totalcost+=fee;turnover+=tv
            same(cash,d['cash'],'rolling cash');check(cash>=-1e-4,'nonnegative cash');same(fee,d['cost'],'daily fees');same(tv,d['turnover'],'daily turnover');check(len(od[day])==int(d['orders']),'daily count')
            actual=hd[day]
            check({c for c,q in units.items() if abs(q)>1e-6}==set(actual),'rolling holdings set '+label+' '+day)
            mv=0.
            for c,h in actual.items():
                q=float(h['normalized_units']);p=float(h['normalized_price']);v=float(h['value']);check(q>=0,'longonly');same(units[c],q,'rolling units',1e-6);same(q*p,v,'holding valuation')
                source=value(c,'close',day)
                if source is None:
                    gaps.append((c,day));source=value(c,'close',day,carry=True)
                same(p,source,'holding source/carried mark');same(v/float(d['account_value']),h['weight'],'weight',1e-10);mv+=v
            same(mv,d['stock_value'],'sum values');same(cash+mv,d['account_value'],'account balance')
            account=float(d['account_value']);check(account>0,'positiveNAV');nav[day]=account;exposure.append(mv/account);high=max(high,account);drawdown=min(drawdown,account/high-1)
        check([(m['instrument'],m['session']) for m in marks]==gaps,'all held quote gaps accounted')
        for m in marks:
            c,day=m['instrument'],m['session'];p=float(hd[day][c]['normalized_price']);same(p,m['marked_normalized_price'],'gap mark bound')
            expected=False;state=states.get(c,{}).get(day,{})
            if state.get('tradestatus')=='0':
                for prior in reversed(calendar[:index[day]]):
                    anchor=value(c,'close',prior)
                    if anchor is None:continue
                    factor=value(c,'factor',prior)
                    try:source=float(states.get(c,{}).get(prior,{}).get('close',''))
                    except (ValueError,TypeError):source=float('nan')
                    expected=(factor is not None and math.isfinite(source) and math.isclose(anchor/factor,source,abs_tol=.005,rel_tol=1e-6) and math.isclose(p,anchor,abs_tol=1e-8,rel_tol=1e-8))
                    if expected:check(m['last_visible_close_date']==prior and m['actual_quote_on_suspended_day_created'] is False,'verified gap provenance')
                    break
            check(type(m['verified']) is bool and m['verified']==expected,'independent halt/mark verification')

        unverified=[m for m in marks if m['verified'] is not True]
        metric={'sessions':485,'net_compound_return_pct':(nav[sessions[-1]]/1000000-1)*100,'2024_return_pct':(nav['2024-12-31']/1000000-1)*100,'2025_return_pct':(nav['2025-12-31']/nav['2024-12-31']-1)*100,'average_exposure_pct':sum(exposure)/485*100,'max_drawdown_pct':drawdown*100,'cost_pct_initial':totalcost/1000000*100,'turnover_x_initial':turnover/1000000,'unverified_held_marks':len(unverified),'orders':len(orders),'unfilled_orders':unfilled}
        for k,v in metric.items():same(v,s[k],'summary '+label+' '+k,1e-8)
        check([i['execution_session'] for i in intents]==monthly,'24 intentions')
        for i in intents:
            day=i['execution_session'];prior=previous[day];check(i['as_of_close_convention']==prior+'T15:05:00+08:00','intent clock')
            same(i['equity_at_decision'],nav[prior],'intent equity')
            priorhold=hd.get(prior,{})
            check(set(i['holdings_at_decision'])==set(priorhold),'intent inventory keys')
            for c,q in i['holdings_at_decision'].items():same(q,priorhold[c]['normalized_units'],'intent units',1e-6)
            check(i['target_weights']==targets[family][day]['weights'],'intent targets')
            check({o['instrument'] for o in i['orders']}=={o['instrument'] for o in od[day]},'intent order codes')
            expected_orders,allocation=independent_allocation(nav[prior],{c:float(h['normalized_units']) for c,h in priorhold.items()},targets[family][day]['weights'],prior,value)
            equivalent(i['orders'],expected_orders)
            equivalent(i['allocation_receipt'],allocation)
            check(i['latest_decision_price_read']==prior and i['execution_exchange_queried_for_decision'] is False,'no execution-day allocation information')
            for o in i['orders']:
                actualo=next(x for x in od[day] if x['instrument']==o['instrument'])
                check(actualo['side']==o['side'],'intent side');same(o['normalized_units'],abs(float(actualo['requested_normalized_units'])),'intent requested units')
        results[label]={'all_485_cash_units_fees_turnover_valuation_checks_passed':True,'all_24_prior_close_intents_verified':True,'all_24_budgeted_allocation_receipts_reconstructed':True,'recomputed_metrics':metric,'unverified_marks':unverified,'artifact_hashes_verified':7,'inherited_rounding_overshoots':rounding_overshoots,'strict_requested_quantity_not_exceeded':not rounding_overshoots}
    primary=results['40/low_market_residual_vol_1m']['recomputed_metrics']
    selected=('low_market_residual_vol_1m' if primary['2024_return_pct']>0 and primary['2025_return_pct']>0 and primary['average_exposure_pct']>=90 and primary['unverified_held_marks']==0 else None)
    check(summary['selected_development_lead']==selected,'only fixed 40bp candidate gate')
    check(summary['objective_achieved'] is False and summary['2026_market_values_queried'] is False and summary['raw_share_execution_verified'] is False and summary['historical_arrival_verified'] is False,'claim boundaries')
    check(digest(PLAN)==EXPECTED,'plan unchanged after audit')
    for n,h in hashes.items():check(digest(OUT/n)==h,'artifact unchanged after audit '+n)
    check(verify_baseline(plan)==baseline_hashes and summary['all42_baseline_financial_bytes_unchanged'] is True,'baseline pre/post preserved')
    check(summary['allocation_trial_id']==plan['allocation_trial_id']=='low_market_residual_vol_1m_budgeted_lots','trial identity')
    report={'status':'PASS_INDEPENDENT_BUDGETED_PRE2026_CSV_ACCOUNT_AUDIT','baseline_financial_hashes_verified':baseline_hashes,'independent_allocation_receipts_rebuilt':144,'freeze_commit':freeze,'plan_sha256':EXPECTED,'summary_sha256':digest(OUT/'summary.json'),'audit_script_sha256':digest(Path(__file__)),'method_hashes_verified':plan['method_code_sha256'],'financial_artifact_hashes_verified':hashes,'all_physical_features_hashed':4010,'source_feature_files_decoded':len(source_hashes),'source_feature_hashes':source_hashes,'results_by_case':results,'case_count':6,'daily_sessions_per_case':485,'NAV_points_including_initial_anchor':486,'prior_close_intents_total':144,'only_selectable_candidate':'low_market_residual_vol_1m','descriptive_controls_selectable':False,'selected_development_lead':selected,'2026_market_data_read':False,'production_reconcile_or_summarize_called':False,'account_replay_rerun':False,'repository_modified':False,'objective_achieved':False,'limitations':['Qlib normalized units and daily-open execution are engineering proxies, not raw-share or exchange executions.','Qlib requested quantity overshoot up to0.10001 physical shares is retained as inherited numerical rounding tolerance, not strict integer-share certification.','Unfilled orders and independently unverified carried marks are retained; a candidate with any unverified mark cannot pass.','No claim of historical arrival, intraday execution or2026outcomes; factor fits are covered by separately bound formation audit.'],'critical_or_important_audit_findings':[]}
    with REPORT.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'report':str(REPORT),'report_sha256':digest(REPORT),'script_sha256':report['audit_script_sha256'],'cases':6,'days_per_case':485,'nav_points':486,'selected':selected}))


def cli():
    global REPO,BASE,OUT,PROVIDER,PLAN,REPORT,EXPECTED,FREEZE,GAPS
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root',default=str(REPO));p.add_argument('--source-root',default=str(BASE))
    for n in ('plan','expected-plan-sha256','freeze-commit','output'):p.add_argument('--'+n,required=True)
    p.add_argument('--gap-states',default=None)
    a=p.parse_args();REPO=Path(a.repo_root).resolve();BASE=Path(a.source_root).resolve()
    OUT=BASE/'low-market-residual-vol1m-budgeted-pre2026-development-20261021';PROVIDER=BASE/'qlib-price-delay-pre2026-clock-v2-20261021'
    PLAN=Path(a.plan).resolve();REPORT=Path(a.output).resolve();EXPECTED=a.expected_plan_sha256;FREEZE=a.freeze_commit
    GAPS=Path(a.gap_states).resolve() if a.gap_states else BASE/'low-risk-gap-states-pre2026-20261017'
    check(not REPORT.exists(),'audit report must be new')
    check(REPORT!=PLAN and OUT not in REPORT.parents and PROVIDER not in REPORT.parents and REPO not in REPORT.parents,'audit output outside immutable artifacts/repository')
    main()

if __name__=='__main__':cli()
