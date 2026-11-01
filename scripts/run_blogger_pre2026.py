"""Frozen three-rule blogger study, full two-year accounts; no2026 entry point."""
import argparse,csv
from importlib import metadata
import json,math
from pathlib import Path
import sys
from scripts.prepare_blogger_etf_data import inventory,sha,write,FUNDS,INDEXES
from stock_rsi.blogger_rotation import NAMES,development_pass
from stock_rsi.qlib_snapshot import QlibSnapshot

START,END='2024-01-02','2025-12-31'
METHODS=('src/stock_rsi/blogger_rotation.py','src/stock_rsi/blogger_qlib_strategy.py','src/stock_rsi/strict_qlib_exchange.py',
 'src/stock_rsi/qlib_snapshot.py','src/stock_rsi/prior_close_orders.py','src/stock_rsi/qlib_daily_evidence.py',
 'scripts/prepare_blogger_etf_data.py','scripts/recover_blogger_etf_sources.py','scripts/prepare_blogger_tencent_data.py',
 'scripts/run_blogger_pre2026.py','scripts/audit_blogger_pre2026.py','scripts/audit_published_strategies.py','scripts/run_qlib_profitability_pre2026.py',
 'tests/test_blogger_rotation.py','docs/research/blogger-strategy-batch-2026-11-01.md',
 'docs/research/blogger-source-recovery-2026-11-01.md')
PROFILE={'status':'FROZEN_THREE_BLOGGER_RULES_PRE2026','candidates':list(NAMES),'candidate_budget':3,'extra_bps':[20,40],
 'base_buy_sell_bps':[5,5],'min_fee_CNY':5,'capital_CNY':1000000,'window':[START,END],
 'target_cap':.95,'average_exposure_is_hard_gate':False,'reference_extra_bps':40,
 'network_during_run':False,'2026_bars_permitted':False,'investment_qualification':False,
 'volume_unit_or_capacity_verified':False,'impact_cost':0}


def read(path):return json.loads(Path(path).read_text())


def config_path(root,name):return root/'skills'/('a-share-blogger-'+name.replace('_','-'))/'skill.json'


def bindings(root,data):
    configs={n:read(config_path(root,n)) for n in NAMES}
    for n,c in configs.items():
        if c['id']!=n or c['target_cap']!=.95 or c['average_exposure_is_hard_gate'] is not False:raise ValueError('frozen rule identity/cap required; no exposure veto')
    sources=read(root/'experiments/blogger-strategies/sources.json')
    if sources['candidate_budget']!=3 or {s['id'] for s in sources['sources'] if s['id'] in ('fengji2016','plus2047_2022')}!={'fengji2016','plus2047_2022'}:raise ValueError('exact disclosed source cohort required')
    source_files={s['local_capture']:s.get('raw_html_sha256',s.get('source_sha256')) for s in sources['sources'] if 'local_capture' in s}
    if any(sha(p)!=h for p,h in source_files.items()):raise ValueError('primary captured source changed')
    snapshot=QlibSnapshot(data/'provider');manifest=read(data/'provider/manifest.json')
    if snapshot.calendar[-1].isoformat()!=END or set(i.symbol for i in snapshot.instruments)!=set(FUNDS+INDEXES):raise ValueError('fixed identities and physically pre2026 quote calendar')
    if {k:v for k,v in inventory(data/'provider').items() if k!='manifest.json'}!=manifest['all_output_sha256']:raise ValueError('derived provider identity changed')
    if read(data/'capture/manifest.json')['status']!='ALL13_CAPTURED':raise ValueError('all13 same-provider inputs required')
    names=list(METHODS)+['experiments/blogger-strategies/sources.json']
    for n in NAMES:names += [str(config_path(root,n).relative_to(root)),str(config_path(root,n).with_name('SKILL.md').relative_to(root))]
    return {'configs':configs,'method_and_source_sha256':{n:sha(root/n) for n in sorted(names)},'captured_article_sha256':source_files,
            'data_sha256':inventory(data),'runtime':{'python':sys.version.split()[0],**{n:metadata.version(n) for n in ('pyqlib','numpy','pandas')}}}


def freeze(root,data,request):write(request,{**PROFILE,**bindings(root,data)});return sha(request)


def verify(root,data,request,expected):
    if sha(request)!=expected:raise ValueError('explicit frozen request mismatch')
    req=read(request)
    if req!={**PROFILE,**bindings(root,data)}:raise ValueError('frozen method, source, skill, data, runtime or profile changed')
    return req


def simulate(provider,config,extra,out):
    import qlib,pandas as pd
    from qlib.constant import REG_CN
    from qlib.backtest import backtest
    from stock_rsi.blogger_qlib_strategy import BloggerPriorCloseStrategy
    from stock_rsi.strict_qlib_exchange import StrictRequestedQuantityExchange
    from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence
    from scripts.run_qlib_profitability_pre2026 import summarize_report
    snapshot=QlibSnapshot(provider);qlib.init(provider_uri=str(provider),region=REG_CN,kernels=1,logging_level=40)
    strategy=BloggerPriorCloseStrategy(config=config,snapshot=snapshot)
    exchange=StrictRequestedQuantityExchange(freq='day',codes=config['symbols'],start_time='2023-12-29',end_time=END,
        deal_price='open',limit_threshold=('$buyblock','$sellblock'),open_cost=(5+extra)/10000,close_cost=(5+extra)/10000,
        min_cost=5,impact_cost=0,volume_threshold=None)
    portfolio,indicators=backtest(start_time=START,end_time=END,strategy=strategy,
        executor={'class':'SimulatorExecutor','module_path':'qlib.backtest.executor','kwargs':{'time_per_step':'day','generate_portfolio_metrics':True}},
        benchmark='SH000300',account=1000000,exchange_kwargs={'exchange':exchange})
    report,positions=portfolio['1day'];expected=pd.DatetimeIndex([d for d in snapshot.calendar if START<=d.isoformat()<=END])
    if not report.index.equals(expected) or strategy.decision_days!=[d.strftime('%Y-%m-%d') for d in expected]:raise ValueError('complete485-session continuous account required')
    for i in strategy.intents:
        day=i['as_of'][:10];prior=pd.Timestamp(day);equity=float(report.loc[prior,'account']) if day>=START else 1000000
        held=positions[prior].get_stock_amount_dict() if day>=START else {}
        if not math.isclose(i['equity_at_decision'],equity,rel_tol=1e-10,abs_tol=.01) or i['holdings_at_decision']!={c:float(q) for c,q in held.items()}:
            raise ValueError('no execution-day account in decision')
    evidence=reconcile_daily_evidence(report,positions,indicators['1day'][1].order_indicator_his,snapshot.calendar,initial_cash=1000000,
        signal_days={pd.Timestamp(r['as_of'][:10]).date() for r in strategy.intents})
    missing=[{'instrument':h['instrument'],'session':h['session']} for h in evidence['holdings'] if snapshot.value(h['instrument'],'close',h['session']) is None]
    for key in ('days','orders','holdings'):pd.DataFrame(evidence[key]).to_csv(out/(key+'.csv'),index=False)
    report.to_pickle(out/'report.pkl');pd.to_pickle(positions,out/'positions.pkl');write(out/'decision_intents.json',strategy.intents);write(out/'missing-held-marks.json',missing)
    return {**summarize_report(report,1000000),'decision_snapshots':len(strategy.intents),'orders':len(evidence['orders']),
        'unfilled_orders':sum(o['fill_status']=='UNFILLED' for o in evidence['orders']),'unverified_held_marks':len(missing),
        'volume_unit_or_capacity_verified':False,'raw_share_account_qualified':False,'source_class':'CURRENT_VINTAGE_ADJUSTED_DAILY_ENGINEERING_PROXY'}


def execute(root,data,request,expected,out):
    req=verify(root,data,request,expected)
    if out.exists():raise ValueError('fresh output only')
    out.mkdir(parents=True);results={};stage='SETUP';terminal={'status':'BLOGGER_STUDY_INCOMPLETE','complete':False,'request_sha256':expected,
        '2026_candidate_returns_computed':False,'average_exposure_is_hard_gate':False,'investment_qualified':False,'objective_achieved':False}
    try:
        for extra in PROFILE['extra_bps']:
            for name in NAMES:
                stage=str(extra)+'/'+name;folder=out/stage;folder.mkdir(parents=True);print('blogger account',stage,flush=True)
                value=simulate(data/'provider',req['configs'][name],extra,folder);write(folder/'metrics.json',value);results[stage]=value
        terminal.update(status='ALL_THREE_BLOGGER_PRE2026_CANDIDATES_COMPLETE',complete=True,results=results,
                        passed_numerical_two_year_screen=[n for n in NAMES if development_pass(results['40/'+n])],
                        scope='fixed batch,2024/2025 only; no adaptive2026 stopping target')
    except BaseException as exc:terminal.update(error_type=type(exc).__name__,error=str(exc),failed_stage=stage);raise
    finally:
        try:terminal['all_inputs_unchanged']=verify(root,data,request,expected)==req
        except BaseException as exc:terminal.update(complete=False,all_inputs_unchanged=False,status='INPUT_CHANGED_RESULTS_QUARANTINED',results={},error=str(exc))
        terminal['artifact_sha256']=inventory(out);write(out/'terminal.json',terminal)
        if not terminal['all_inputs_unchanged']:raise ValueError('inputs changed; all results quarantined')
    return terminal


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','preflight','run'])
    for n in ('data','request'):p.add_argument('--'+n,required=True)
    p.add_argument('--expected-sha256');p.add_argument('--out');a=p.parse_args();root=Path(__file__).resolve().parents[1];data=Path(a.data).resolve();request=Path(a.request).resolve()
    if a.mode=='freeze':print(freeze(root,data,request));return
    if not a.expected_sha256:p.error('explicit frozen request SHA256 required')
    if a.mode=='preflight':verify(root,data,request,a.expected_sha256);print('preflight PASS');return
    if not a.out:p.error('fresh output required')
    print(execute(root,data,request,a.expected_sha256,Path(a.out).resolve())['status'])


if __name__=='__main__':main()
