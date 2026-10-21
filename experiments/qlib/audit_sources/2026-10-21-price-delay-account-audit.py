"""Independent stdlib CSV audit. No production imports, pickle loading or replay.
Reads only a physically pre2026 provider; Jan2026 metadata is never a quote.
"""
from pathlib import Path
from collections import defaultdict
import csv, hashlib, json, math, struct, subprocess

REPO=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
OUT=BASE/'price-delay-clock-v2-pre2026-development-20261021'
PROVIDER=BASE/'qlib-price-delay-pre2026-clock-v2-20261021'
PLAN=REPO/'experiments/qlib/price-delay-clock-v2-pre2026-development-plan.json'
REPORT=Path('/tmp/price-delay-pre2026-account-independent-review-20261021.json')
EXPECTED='f4d425b1eda9ad6f1253337ca393870b54a2577c26042595bff2e6c0c6d0f94f'

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def csvrows(p):
    with p.open() as f:return list(csv.DictReader(f))
def check(v,label):
    if not v:raise AssertionError(label)
def same(a,b,label,absolute=2e-5):
    check(math.isfinite(float(a)) and math.isfinite(float(b)) and math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=absolute),f'{label}: {a} != {b}')

def main():
    plan=read(PLAN); summary=read(OUT/'summary.json')
    check(digest(PLAN)==EXPECTED==summary['plan_sha256'],'external plan')
    freeze=subprocess.check_output(['git','rev-parse','3bfca8d'],cwd=REPO,text=True).strip()
    check(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(PLAN.relative_to(REPO))],cwd=REPO)).hexdigest()==EXPECTED,'freeze plan')
    check(summary['method_code_sha256']==plan['method_code_sha256'],'summary methods')
    for n,h in plan['method_code_sha256'].items():
        check(digest(REPO/n)==h,'current method '+n)
        check(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=REPO)).hexdigest()==h,'frozen method '+n)
    check(plan['families']==['price_delay_d1'] and set(plan['descriptive_controls'])=={'low_delay_control','eligible_equal_weight'} and plan['candidate_budget']==1,'single selectable candidate')
    manifest=read(PROVIDER/'manifest.json');check(digest(PROVIDER/'manifest.json')==plan['provider_manifest_sha256'],'provider manifest')
    check(manifest['all_output_values_at_or_before']=='2025-12-31','pre2026 provider')
    calendar=(PROVIDER/'calendars/day.txt').read_text().splitlines()
    check(calendar==sorted(set(calendar)) and calendar[-1]=='2025-12-31' and digest(PROVIDER/'calendars/day.txt')==plan['input_sha256']['calendars/day.txt'],'calendar')
    sessions=[d for d in calendar if '2024-01-02'<=d<='2025-12-31'];check(len(sessions)==485,'485')
    previous={calendar[i]:calendar[i-1] for i in range(1,len(calendar))};index={d:i for i,d in enumerate(calendar)}
    monthly=[]
    for d in sessions:
        if not monthly or monthly[-1][:7]!=d[:7]:monthly.append(d)
    check(len(monthly)==24,'monthly clock')
    targets=read(OUT/'targets.json');receipts=read(OUT/'formation_receipts.json')
    check(digest(OUT/'targets.json')==summary['targets_sha256']==plan['initial_targets_sha256'],'targets')
    check(digest(OUT/'formation_receipts.json')==summary['formation_receipts_sha256']==plan['initial_receipts_sha256'],'receipts')
    check(set(targets)=={'price_delay_d1','low_delay_control','eligible_equal_weight'},'target families')
    for f,t in targets.items():
        check(list(t)==monthly,'24 targets '+f)
        for d,v in t.items():check(v['as_of']==previous[d],'target prior '+f)
    check([r['execution_session'] for r in receipts]==monthly,'receipt clock')
    for r in receipts:
        check(r['formation_asof']==previous[r['execution_session']] and r['latest_formation_price_read']==r['formation_asof'] and r['latest_measurement_price_read']<=r['measurement_cap']<r['formation_asof'],'receipt lag')
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
        for o in orders:check(o['session'] in sessions,'order day');od[o['session']].append(o)
        for h in holdings:check(h['session'] in sessions and h['instrument'] not in hd[h['session']],'unique holding');hd[h['session']][h['instrument']]=h
        cash=1000000.;units=defaultdict(float);totalcost=turnover=0.;unfilled=0;nav={'2023-12-29':1000000.};exposure=[];high=1000000.;drawdown=0.;gaps=[]
        for d in days:
            day=d['session'];prior=previous[day];check(d['signal_date']==prior and d['signal_bar_close_convention']==prior+'T15:00:00+08:00','daily priorclose')
            check((d['signal_present']=='True')==(prior in {v['as_of'] for v in targets[family].values()}),'signal presence')
            fee=tv=signed=0.
            for o in od[day]:
                check(o['signal_date']==prior and prior in {v['as_of'] for v in targets[family].values()},'order signal')
                side=o['side'];check(side in ('BUY','SELL'),'side');sign=1 if side=='BUY' else -1
                q=float(o['filled_normalized_units']);amount=float(o['requested_normalized_units']);gross=float(o['signed_trade_value']);c=float(o['cost'])
                check(math.isfinite(q) and math.isfinite(amount) and sign*q>=0 and sign*amount>=0,'signed units');check(abs(q)<=abs(amount)+.10001/value(o['instrument'],'factor',day),'filled vs requested rounding allowance')
                check(sign*gross>=0 and c>=0,'signed gross/cost')
                if o['fill_status']=='UNFILLED':
                    check(q==gross==c==0,'unfilled cash');unfilled+=1
                else:
                    check(o['fill_status']=='FILLED_OR_PARTIAL' and sign*q>0,'fill status');price=float(o['normalized_price']);same(q*price,gross,'gross identity')
                    same(price,value(o['instrument'],'open',day),'open source')
                    rate=(.0005 if sign==1 else .0015)+cost/10000;same(max(5,abs(gross)*rate),c,'fee rule')
                units[o['instrument']]+=q;fee+=c;tv+=abs(gross);signed+=gross
            cash-=signed+fee;totalcost+=fee;turnover+=tv
            same(cash,d['cash'],'rolling cash');same(fee,d['cost'],'daily fees');same(tv,d['turnover'],'daily turnover');check(len(od[day])==int(d['orders']),'daily count')
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
        for m in marks:same(float(hd[m['session']][m['instrument']]['normalized_price']),m['marked_normalized_price'],'gap mark bound')
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
            for o in i['orders']:
                check(o['as_of']==prior,'intent order clock')
                held=float(i['holdings_at_decision'].get(o['instrument'],0));weight=i['target_weights'].get(o['instrument'],0)
                if o['quantity_basis']=='KNOWN_INVENTORY_FULL_EXIT':
                    check(weight==0 and o['side']=='SELL' and o['known_normalized_close'] is None and o['known_factor'] is None,'inventory exit basis');same(o['normalized_units'],held,'full exit known units')
                else:
                    check(o['quantity_basis']=='PRIOR_CLOSE_TARGET','known sizing basis')
                    p=value(o['instrument'],'close',prior);f=value(o['instrument'],'factor',prior)
                    same(o['known_normalized_close'],p,'intent source price');same(o['known_factor'],f,'intent source factor')
                    desired=math.floor(float(i['equity_at_decision'])*weight/p*f/100+1e-10)*100/f
                    delta=desired-held
                    if o['side']=='BUY':expected=math.floor(delta*f/100+1e-10)*100/f;check(delta>0,'buy target delta')
                    else:expected=-delta;check(delta<0,'sell target delta')
                    same(o['normalized_units'],expected,'prior close target sizing')
                actualo=next(x for x in od[day] if x['instrument']==o['instrument']);check(actualo['side']==o['side'],'intent side');same(o['normalized_units'],abs(float(actualo['requested_normalized_units'])),'intent requested units')
        results[label]={'all_485_cash_units_fees_turnover_valuation_checks_passed':True,'all_24_prior_close_intents_verified':True,'recomputed_metrics':metric,'unverified_marks':unverified,'artifact_hashes_verified':7}
    blocked=results['40/price_delay_d1']['unverified_marks'];check(len(blocked)==3 and [(m['instrument'],m['session']) for m in blocked]==[('SH601298',d) for d in ['2024-07-10','2024-07-11','2024-07-12']],'specific candidate blocker')
    check(summary['selected_development_lead'] is None and summary['objective_achieved'] is False and summary['2026_market_values_queried'] is False,'selection/no2026')
    report={'status':'PASS_INDEPENDENT_CSV_AUDIT_WITH_SELECTION_BLOCKED','freeze_commit':freeze,'plan_sha256':EXPECTED,'summary_sha256':digest(OUT/'summary.json'),'audit_script_sha256':digest(Path(__file__)),'method_hashes_verified':plan['method_code_sha256'],'financial_artifact_hashes_verified':hashes,'source_feature_files_hashed_and_read':len(source_hashes),'source_feature_hashes':source_hashes,'results_by_case':results,'only_selectable_candidate':'price_delay_d1','descriptive_controls_selectable':False,'selected_development_lead':None,'selection_blocker':'The sole candidate has three independently unverified held quote marks: SH601298 on2024-07-10/11/12. Positive annual returns and >=90% exposure do not satisfy the required no-unverified-marks gate. Control performance cannot substitute another candidate.','2026_market_data_read':False,'production_reconcile_or_summarize_called':False,'account_replay_rerun':False,'repository_modified':False,'v1_failure_outputs_modified':False,'objective_achieved':False,'limitations':['Qlib normalized units, daily-open execution and normalized marks are engineering proxies, not raw-share or exchange executions.','Unverified carried marks remain unresolved; arithmetic agreement does not authenticate suspension state.','Evidence is nonsealed; historical source arrival, raw-share intraday execution and2026outcomes are unverified.'],'critical_or_important_audit_findings':[]}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(REPORT),'report_sha256':digest(REPORT),'script_sha256':report['audit_script_sha256'],'cases':6,'days_per_case':485,'artifact_hashes':len(hashes),'methods':len(plan['method_code_sha256']),'source_features':len(source_hashes),'selected':None}))

if __name__=='__main__':main()
