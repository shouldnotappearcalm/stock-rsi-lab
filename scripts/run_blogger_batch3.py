"""Monthly and annual blogger study, preserving all earlier strategy files."""
import argparse,csv,json,math,sys
from importlib import metadata
from pathlib import Path
from scripts.prepare_blogger_etf_data import inventory,sha,write
from scripts.run_published_strategies_2026 import per_year,compare_prefix
from scripts.published_replay_float_comparison import compare_original
from stock_rsi.blogger_batch3 import NAMES,STOCK as CODE,BOND
from stock_rsi.blogger_rotation import development_pass
from stock_rsi.qlib_snapshot import QlibSnapshot

PRESERVED='experiments/strategy-library/retained-before-batch3-2026-11-01.json'
METHODS=('src/stock_rsi/blogger_batch3.py','src/stock_rsi/blogger_batch3_qlib.py','src/stock_rsi/blogger_qlib_strategy.py',
 'src/stock_rsi/strict_qlib_exchange.py','src/stock_rsi/prior_close_orders.py','src/stock_rsi/qlib_snapshot.py',
 'src/stock_rsi/qlib_daily_evidence.py','src/stock_rsi/data.py','src/stock_rsi/blogger_rotation.py',
 'scripts/prepare_blogger_batch3_data.py','scripts/run_blogger_batch3.py','scripts/audit_blogger_batch3.py',
 'scripts/audit_blogger_batch2.py','scripts/audit_blogger_2026.py','scripts/audit_blogger_pre2026.py',
 'scripts/audit_published_strategies.py','scripts/audit_published_strategies_2026.py','scripts/audit_published_strategy_execution.py',
 'scripts/published_replay_float_comparison.py','scripts/run_published_strategies_2026.py','scripts/run_qlib_profitability_pre2026.py',
 'tests/test_blogger_batch3.py','docs/research/blogger-batch3-plan-2026-11-01.md',PRESERVED,'experiments/blogger-batch3/sources.json')

def read(p):return json.loads(Path(p).read_text())
def rows(p):
    with Path(p).open() as f:return list(csv.DictReader(f))

def preserved(root):
    manifest=read(root/PRESERVED)
    if not all(sha(root/n)==h for n,h in manifest['files_sha256'].items()):raise ValueError('retained old strategy or evidence changed')
    return manifest['files_sha256']

def selected(phase,dev):
    if phase=='development':return list(NAMES)
    if dev is None:raise ValueError('actual prior development run required')
    t=read(dev/'terminal.json')
    if not t['complete'] or not t['all_inputs_unchanged'] or t['phase']!='development':raise ValueError('complete unchanged development required')
    candidates=[n for n in NAMES if development_pass(t['results']['40/'+n])]
    if not candidates or candidates!=t['passed_two_year_screen']:raise ValueError('only all passing development candidates may run2026')
    return candidates

def context(root,data,phase,dev):
    end='2025-12-31' if phase=='development' else '2026-10-30';names=selected(phase,dev);snapshot=QlibSnapshot(data/'provider')
    if snapshot.calendar[-1].isoformat()!=end or snapshot.calendar[0].isoformat()!='2022-12-01' or {i.symbol for i in snapshot.instruments}!={CODE,BOND}:raise ValueError('two source identities, fixed warmup and physically capped phase')
    manifest=read(data/'provider/manifest.json')
    if {n:h for n,h in inventory(data/'provider').items() if n!='manifest.json'}!=manifest['all_output_sha256']:raise ValueError('provider changed')
    configs={n:read(root/'skills'/('a-share-blogger-'+n)/'skill.json') for n in NAMES};methods=list(METHODS)
    for n,c in configs.items():
        if c['id']!=n or c['symbols']!=([CODE] if n=='faber10' else [CODE,BOND]) or c['target_cap']!=.95 or c['average_exposure_is_hard_gate'] is not False:raise ValueError('same predeclared identities/budget and no exposure veto')
        if c['schedule']!=('MONTH_END_COMPLETED_SESSIONS' if n=='faber10' else 'YEAR_END_COMPLETED_SESSIONS') or n=='glaozi50' and c['weights']!={CODE:.475,BOND:.475}:raise ValueError('descriptor must match literal frozen schedule and weights')
        methods += [str(Path('skills')/('a-share-blogger-'+n)/f) for f in ('skill.json','SKILL.md')]
    dev_request_hash=None
    if phase=='forward':
        dev_request=root/'experiments/blogger-batch3/development-request.json';terminal=read(dev/'terminal.json');dev_request_hash=sha(dev_request)
        if dev_request_hash!=terminal['request_sha256'] or inventory(dev)!={**terminal['artifact_sha256'],'terminal.json':sha(dev/'terminal.json')}:raise ValueError('actual development outputs and frozen request required')
        original_data=Path(read(data/'preparation.json')['development_data_root'])
        if read(dev_request)!=context(root,original_data,'development',None):raise ValueError('development method, source, data, runtime or rules changed before forward')
    elif dev is not None:raise ValueError('development cannot take a forward selection input')
    sources=read(root/'experiments/blogger-batch3/sources.json');articles={s['capture']:s['sha256'] for s in sources['sources'] if 'capture' in s}
    if any(sha(p)!=h for p,h in articles.items()):raise ValueError('original source capture changed')
    return {'phase':phase,'end':end,'candidates':names,'candidate_budget':2,'extra_bps':[20,40],'capital_CNY':1000000,
        'base_buy_sell_bps':[5,5],'minimum_fee_CNY':5,'average_exposure_is_hard_gate':False,'configs':configs,
        'year2026_baseline':'2025_FINAL_NAV_NO_RESET','2026_results_may_change_rules':False,'is_new_sealed_holdout':False,
        'investment_qualified':False,'runtime':{'python':sys.version.split()[0],**{n:metadata.version(n) for n in ('pyqlib','numpy','pandas')}},
        'method_and_source_sha256':{n:sha(root/n) for n in sorted(methods)},'data_sha256':inventory(data),'captured_article_sha256':articles,
        'retained_prior_files_sha256':preserved(root),'development_request_sha256':dev_request_hash,'development_run_sha256':inventory(dev) if dev is not None else None}

def freeze(root,data,phase,dev,request):write(request,context(root,data,phase,dev));return sha(request)
def verify(root,data,phase,dev,request,expected):
    if sha(request)!=expected or read(request)!=context(root,data,phase,dev):raise ValueError('frozen request or inputs changed')
    return read(request)

def simulate(provider,config,extra,out):
    import qlib,pandas as pd
    from qlib.constant import REG_CN
    from qlib.backtest import backtest
    from stock_rsi.blogger_batch3_qlib import Batch3Strategy
    from stock_rsi.strict_qlib_exchange import StrictRequestedQuantityExchange
    from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence
    from scripts.run_qlib_profitability_pre2026 import summarize_report
    snapshot=QlibSnapshot(provider);end=snapshot.calendar[-1].isoformat();qlib.init(provider_uri=str(provider),region=REG_CN,kernels=1,logging_level=40)
    strategy=Batch3Strategy(config=config,snapshot=snapshot,extra=extra)
    exchange=StrictRequestedQuantityExchange(freq='day',codes=config['symbols'],start_time='2023-12-29',end_time=end,
        deal_price='open',limit_threshold=('$buyblock','$sellblock'),open_cost=(5+extra)/10000,close_cost=(5+extra)/10000,min_cost=5,impact_cost=0,volume_threshold=None)
    portfolio,indicators=backtest(start_time='2024-01-02',end_time=end,strategy=strategy,
        executor={'class':'SimulatorExecutor','module_path':'qlib.backtest.executor','kwargs':{'time_per_step':'day','generate_portfolio_metrics':True}},
        benchmark=CODE,account=1000000,exchange_kwargs={'exchange':exchange})
    report,positions=portfolio['1day'];expected=pd.DatetimeIndex([d for d in snapshot.calendar if d.isoformat()>='2024-01-02'])
    if not report.index.equals(expected) or [i['execution_session'] for i in strategy.intents]!=[d.strftime('%Y-%m-%d') for d in expected]:raise ValueError('complete continuous account sessions required')
    for i in strategy.intents:
        d=i['as_of'][:10];prior=pd.Timestamp(d);equity=float(report.loc[prior,'account']) if d>='2024-01-02' else 1000000
        held=positions[prior].get_stock_amount_dict() if d>='2024-01-02' else {}
        if not math.isclose(i['equity_at_decision'],equity,rel_tol=1e-10,abs_tol=.01) or i['holdings_at_decision']!={c:float(q) for c,q in held.items()}:raise ValueError('prior actual account only')
    evidence=reconcile_daily_evidence(report,positions,indicators['1day'][1].order_indicator_his,snapshot.calendar,initial_cash=1000000,
        signal_days={pd.Timestamp(i['as_of'][:10]).date() for i in strategy.intents})
    missing=[{'instrument':h['instrument'],'session':h['session']} for h in evidence['holdings'] if snapshot.value(h['instrument'],'close',h['session']) is None]
    for key in ('days','orders','holdings'):pd.DataFrame(evidence[key]).to_csv(out/(key+'.csv'),index=False)
    report.to_pickle(out/'report.pkl');pd.to_pickle(positions,out/'positions.pkl');write(out/'decision_intents.json',strategy.intents);write(out/'missing-held-marks.json',missing)
    return {**summarize_report(report,1000000),'per_year':per_year(evidence['days']),'orders':len(evidence['orders']),
        'unfilled_orders':sum(o['fill_status']=='UNFILLED' for o in evidence['orders']),'unverified_held_marks':len(missing),'decision_snapshots':len(strategy.intents),
        'investment_qualified':False,'opening_capacity_verified':False}

def run(root,data,phase,dev,request,expected,out):
    req=verify(root,data,phase,dev,request,expected)
    if out.exists():raise ValueError('fresh output only')
    out.mkdir(parents=True);results={};prefix={};stage='SETUP';terminal={'complete':False,'status':'BATCH3_INCOMPLETE','phase':phase,'request_sha256':expected,
        '2026_returns_computed':False,'investment_qualified':False,'objective_achieved':False,'average_exposure_is_hard_gate':False,'2026_results_used_to_change_rules':False}
    try:
        phases=[('development',data/'provider')] if phase=='development' else [('baseline',Path(read(data/'preparation.json')['development_data_root'])/'provider'),('forward',data/'provider')]
        for step,provider in phases:
            for extra in (20,40):
                for n in req['candidates']:
                    case=str(extra)+'/'+n;stage=case if phase=='development' else step+'/'+case;folder=out/stage;folder.mkdir(parents=True);print(phase,stage,flush=True)
                    if step=='forward':terminal['2026_returns_computed']=True
                    metric=simulate(provider,req['configs'][n],extra,folder);write(folder/'metrics.json',metric);results[stage]=metric
                    if step=='baseline':prefix[stage]=compare_original(dev/case,folder)
                    if step=='forward':prefix[stage]=compare_prefix(out/'baseline'/case,folder)
        terminal.update(complete=True,status='BATCH3_'+phase.upper()+'_COMPLETE',results=results,prefix_checks=prefix)
        if phase=='development':terminal['passed_two_year_screen']=[n for n in NAMES if development_pass(results['40/'+n])]
        else:
            terminal['actual_2026_return_ge10_by_case']={k.removeprefix('forward/'):m['per_year']['2026']['net_return_pct']>=10 for k,m in results.items() if k.startswith('forward/')}
            terminal['actual_2026_return_ge20_by_case']={k.removeprefix('forward/'):m['per_year']['2026']['net_return_pct']>=20 for k,m in results.items() if k.startswith('forward/')}
    except BaseException as e:terminal.update(error_type=type(e).__name__,error=str(e),failed_stage=stage);raise
    finally:
        try:terminal['all_inputs_unchanged']=verify(root,data,phase,dev,request,expected)==req
        except BaseException as e:terminal.update(complete=False,status='INPUT_CHANGED_RESULTS_QUARANTINED',all_inputs_unchanged=False,results={},error=str(e))
        terminal['artifact_sha256']=inventory(out);write(out/'terminal.json',terminal)
        if not terminal['all_inputs_unchanged']:raise ValueError('changed inputs, quarantine all results')
    return terminal

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','preflight','run']);p.add_argument('--phase',choices=['development','forward'],required=True)
    for n in ('data','request'):p.add_argument('--'+n,required=True)
    for n in ('development-run','expected-sha256','out'):p.add_argument('--'+n)
    a=p.parse_args();root=Path(__file__).resolve().parents[1];args=(root,Path(a.data).resolve(),a.phase,Path(a.development_run).resolve() if a.development_run else None,Path(a.request).resolve())
    if a.mode=='freeze':print(freeze(*args));return
    if not a.expected_sha256:p.error('explicit frozen request SHA256 required')
    if a.mode=='preflight':verify(*args,a.expected_sha256);print('preflight PASS');return
    if not a.out:p.error('fresh output required')
    print(run(*args,a.expected_sha256,Path(a.out).resolve())['status'])

if __name__=='__main__':main()
