"""Frozen blogger rules on continuous accounts; all six cases, no retuning."""
import argparse,csv,json,math
from pathlib import Path
from scripts import run_blogger_pre2026 as base
from scripts.prepare_blogger_etf_data import inventory,sha,write,FUNDS,INDEXES
from scripts.prepare_blogger_2026_data import END,FIELDS
from scripts.published_replay_float_comparison import compare_original
from scripts.run_published_strategies_2026 import per_year,compare_prefix

OLD_REQUEST='experiments/blogger-strategies/development-request.json'
OLD_SHA='994e17940bd02d4132895a2c688504933f2b1b2d1d807b998ddd3f123eed4266'
OLD_TERMINAL='experiments/blogger-strategies/pre2026-results/terminal.json'
METHODS=('scripts/prepare_blogger_2026_data.py','scripts/run_blogger_2026.py','scripts/audit_blogger_2026.py',
         'scripts/run_published_strategies_2026.py','scripts/published_replay_float_comparison.py',
         'scripts/audit_published_strategies_2026.py','scripts/audit_published_strategy_execution.py',
         'tests/test_blogger_2026.py','docs/research/blogger-2026-plan-2026-11-01.md',
         'docs/research/blogger-2026-reference-source-fix-2026-11-01.md')
PROFILE={'status':'FROZEN_THREE_BLOGGER_RULES_THROUGH_20261030','candidates':list(base.NAMES),'candidate_budget':3,
         'extra_bps':[20,40],'continuous_start':'2024-01-02','end':END,'year2026_baseline':'2025_FINAL_NAV_NO_RESET',
         '2026_results_may_change_rules_or_selection':False,'average_exposure_is_hard_gate':False,
         'source_evidence':'EXACT_OLD_PREFIX_TENCENT_PRICE_TAIL_BAOSTOCK_REFERENCE_ENGINEERING_ONLY',
         'original_replay_float_policy':'NAV_WEIGHT_ONLY_8ULP_EXACT_MARKET_AND_TRADES',
         'same_process_forward_prefix_policy':'EXACT_ALL_FIELDS_AND_SNAPSHOT_HASHES','is_new_sealed_holdout':False,
         'network_during_run':False,'investment_qualified':False,'2026_reported_thresholds_pct':[10,20]}


def read(p):return json.loads(Path(p).read_text())
def rows(p):
    with Path(p).open() as f:return list(csv.DictReader(f))


def validate_selection(terminal):
    if terminal['passed_numerical_two_year_screen']!=list(base.NAMES):raise ValueError('all three previously passing candidates required')
    if terminal['average_exposure_is_hard_gate'] is not False:raise ValueError('no invented exposure veto')
    for n in base.NAMES:
        if not base.development_pass(terminal['results']['40/'+n]):raise ValueError('positive complete2024/2025 required')


def data_admission(old,data):
    prep=read(data/'preparation.json');manifest=read(data/'provider/manifest.json')
    if prep['old_input_sha256']!=inventory(old) or prep['all72_feature_prefixes_identical'] is not True:raise ValueError('old inputs and declared72 prefixes required')
    if read(data/'capture/manifest.json')['status']!='ALL13_CAPTURED_AND_OVERLAPS_EXACT':raise ValueError('complete exact-overlap capture required')
    old_cal=(old/'provider/calendars/day.txt').read_text().splitlines();cal=(data/'provider/calendars/day.txt').read_text().splitlines()
    if cal[:len(old_cal)]!=old_cal or cal[-1]!=END:raise ValueError('original clock prefix and complete October required')
    count=0
    for c in FUNDS+INDEXES:
        for f in FIELDS:
            rel=Path('features')/c.lower()/(f+'.day.bin');blob=(old/'provider'/rel).read_bytes();new=(data/'provider'/rel).read_bytes()
            if new[:len(blob)]!=blob or len(new)!=4*(len(cal)+1):raise ValueError('old price prefix or complete current feature changed')
            count+=1
    if count!=72 or {k:v for k,v in inventory(data/'provider').items() if k!='manifest.json'}!=manifest['all_output_sha256']:raise ValueError('whole provider identity required')


def context(root,old_data,data,old_run):
    original=base.verify(root,old_data,root/OLD_REQUEST,OLD_SHA);terminal=read(root/OLD_TERMINAL);validate_selection(terminal)
    if sha(old_run/'terminal.json')!=sha(root/OLD_TERMINAL) or inventory(old_run)!={**terminal['artifact_sha256'],'terminal.json':sha(old_run/'terminal.json')}:raise ValueError('whole original actual output identity required')
    data_admission(old_data,data)
    return {'configs':original['configs'],'runtime':original['runtime'],'old_request_sha256':OLD_SHA,
            'method_and_source_sha256':{**original['method_and_source_sha256'],**{n:sha(root/n) for n in METHODS}},
            'public_sha256':{n:sha(root/n) for n in (OLD_REQUEST,OLD_TERMINAL)},'old_data_sha256':inventory(old_data),
            'data_sha256':inventory(data),'old_run_sha256':inventory(old_run),'captured_article_sha256':original['captured_article_sha256']}


def freeze(root,old,data,old_run,request):write(request,{**PROFILE,**context(root,old,data,old_run)});return sha(request)


def verify(root,old,data,old_run,request,expected):
    if sha(request)!=expected:raise ValueError('explicit forward request SHA256 required')
    value=read(request)
    if value!={**PROFILE,**context(root,old,data,old_run)}:raise ValueError('frozen inputs, methods, profile or runtime changed')
    return value


def simulate(provider,config,extra,out,end):
    import qlib,pandas as pd
    from qlib.constant import REG_CN
    from qlib.backtest import backtest
    from stock_rsi.blogger_qlib_strategy import BloggerPriorCloseStrategy
    from stock_rsi.strict_qlib_exchange import StrictRequestedQuantityExchange
    from stock_rsi.qlib_snapshot import QlibSnapshot
    from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence
    from scripts.run_qlib_profitability_pre2026 import summarize_report
    snapshot=QlibSnapshot(provider)
    if snapshot.calendar[-1].isoformat()!=end:raise ValueError('exact capped end required')
    qlib.init(provider_uri=str(provider),region=REG_CN,kernels=1,logging_level=40)
    strategy=BloggerPriorCloseStrategy(config=config,snapshot=snapshot)
    exchange=StrictRequestedQuantityExchange(freq='day',codes=config['symbols'],start_time='2023-12-29',end_time=end,
        deal_price='open',limit_threshold=('$buyblock','$sellblock'),open_cost=(5+extra)/10000,close_cost=(5+extra)/10000,
        min_cost=5,impact_cost=0,volume_threshold=None)
    portfolio,indicators=backtest(start_time='2024-01-02',end_time=end,strategy=strategy,
        executor={'class':'SimulatorExecutor','module_path':'qlib.backtest.executor','kwargs':{'time_per_step':'day','generate_portfolio_metrics':True}},
        benchmark='SH000300',account=1000000,exchange_kwargs={'exchange':exchange})
    report,positions=portfolio['1day'];expected=pd.DatetimeIndex([d for d in snapshot.calendar if d.isoformat()>='2024-01-02'])
    if not report.index.equals(expected) or strategy.decision_days!=[d.strftime('%Y-%m-%d') for d in expected]:raise ValueError('all continuous account sessions required')
    for i in strategy.intents:
        day=i['as_of'][:10];prior=pd.Timestamp(day);equity=float(report.loc[prior,'account']) if day>='2024-01-02' else 1000000
        held=positions[prior].get_stock_amount_dict() if day>='2024-01-02' else {}
        if not math.isclose(i['equity_at_decision'],equity,rel_tol=1e-10,abs_tol=.01) or i['holdings_at_decision']!={c:float(q) for c,q in held.items()}:raise ValueError('prior actual account only')
    evidence=reconcile_daily_evidence(report,positions,indicators['1day'][1].order_indicator_his,snapshot.calendar,initial_cash=1000000,
        signal_days={pd.Timestamp(i['as_of'][:10]).date() for i in strategy.intents})
    missing=[{'instrument':h['instrument'],'session':h['session']} for h in evidence['holdings'] if snapshot.value(h['instrument'],'close',h['session']) is None]
    for key in ('days','orders','holdings'):pd.DataFrame(evidence[key]).to_csv(out/(key+'.csv'),index=False)
    report.to_pickle(out/'report.pkl');pd.to_pickle(positions,out/'positions.pkl');write(out/'decision_intents.json',strategy.intents);write(out/'missing-held-marks.json',missing)
    return {**summarize_report(report,1000000),'per_year':per_year(evidence['days']),'orders':len(evidence['orders']),
            'unfilled_orders':sum(o['fill_status']=='UNFILLED' for o in evidence['orders']),'decision_snapshots':len(strategy.intents),
            'unverified_held_marks':len(missing),'volume_unit_or_capacity_verified':False,'raw_share_account_qualified':False}


def run(root,old,data,old_run,request,expected,out):
    req=verify(root,old,data,old_run,request,expected)
    if out.exists():raise ValueError('fresh result directory required')
    out.mkdir(parents=True);results={};checks={};stage='SETUP'
    terminal={'status':'BLOGGER_FORWARD_INCOMPLETE','complete':False,'request_sha256':expected,'investment_qualified':False,
              'objective_achieved':False,'2026_results_used_to_change_rules':False,'average_exposure_is_hard_gate':False}
    try:
        for phase,provider,end in [('baseline',old/'provider','2025-12-31'),('forward',data/'provider',END)]:
            for extra in (20,40):
                for name in base.NAMES:
                    label=str(extra)+'/'+name;stage=phase+'/'+label;folder=out/stage;folder.mkdir(parents=True);print(stage,flush=True)
                    metric=simulate(provider,req['configs'][name],extra,folder,end);write(folder/'metrics.json',metric);results[stage]=metric
                    checks[stage]=compare_original(old_run/label,folder) if phase=='baseline' else compare_prefix(out/'baseline'/label,folder)
        terminal.update(status='ALL_THREE_FROZEN_BLOGGER_2026_ACCOUNTS_COMPLETE',complete=True,results=results,prefix_checks=checks,
            period_2026=['2026-01-05',END],no_yearly_account_reset=True,
            actual_2026_return_ge10_by_case={str(e)+'/'+n:results['forward/'+str(e)+'/'+n]['per_year']['2026']['net_return_pct']>=10 for e in (20,40) for n in base.NAMES},
            actual_2026_return_ge20_by_case={str(e)+'/'+n:results['forward/'+str(e)+'/'+n]['per_year']['2026']['net_return_pct']>=20 for e in (20,40) for n in base.NAMES})
    except BaseException as exc:terminal.update(error_type=type(exc).__name__,error=str(exc),failed_stage=stage);raise
    finally:
        try:terminal['all_inputs_unchanged']=verify(root,old,data,old_run,request,expected)==req
        except BaseException as exc:terminal.update(complete=False,all_inputs_unchanged=False,status='INPUT_CHANGED_RESULTS_QUARANTINED',results={},error=str(exc))
        terminal['artifact_sha256']=inventory(out);write(out/'terminal.json',terminal)
        if not terminal['all_inputs_unchanged']:raise ValueError('inputs changed; all results quarantined')
    return terminal


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','preflight','run'])
    for n in ('old-data','data','old-run','request'):p.add_argument('--'+n,required=True)
    p.add_argument('--expected-sha256');p.add_argument('--out');a=p.parse_args();root=Path(__file__).resolve().parents[1]
    args=[root,*[Path(v).resolve() for v in (a.old_data,a.data,a.old_run,a.request)]]
    if a.mode=='freeze':print(freeze(*args));return
    if not a.expected_sha256:p.error('explicit frozen request SHA256 required')
    if a.mode=='preflight':verify(*args,a.expected_sha256);print('preflight PASS');return
    if not a.out:p.error('fresh output required')
    print(run(*args,a.expected_sha256,Path(a.out).resolve())['status'])


if __name__=='__main__':main()
