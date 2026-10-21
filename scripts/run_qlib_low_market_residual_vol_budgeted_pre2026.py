"""Frozen existing budgeted-lot allocation of one-month residual volatility, with no 2026 market queries.

Qlib normalized inventory and daily-open execution are screening proxies.
Any retained lead must separately pass raw-share intraday account replay.
"""
import argparse
import hashlib
import json
import math
from datetime import date
from pathlib import Path

from scripts.run_qlib_low_risk_pre2026 import (
    METHOD_FILES as SHARED_FILES, OPEN_LIMITS, input_hashes, load_state_capture, parse_memberships,
)
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.low_market_residual_vol import CONTROL, FAMILIES, START, END, build_targets
from stock_rsi.return_families import choose_development_lead
from stock_rsi.suspension_evidence import verify_suspension_mark


CAPITAL=1000000
EXTRA_BPS=(20,40)
METHOD_FILES=tuple(dict.fromkeys((*SHARED_FILES,'scripts/run_cninfo_orj_signal_pre2026.py',
    'scripts/prepare_qlib_master_market_pre2026.py','scripts/run_qlib_low_market_residual_vol_budgeted_pre2026.py',
    'scripts/prepare_price_delay_clock_pre2026.py',
    'src/stock_rsi/return_families.py','src/stock_rsi/low_market_residual_vol.py',
    'src/stock_rsi/budgeted_lot_orders.py','src/stock_rsi/budgeted_qlib_strategy.py')))
BASELINE_PREFIX = 'experiments/qlib/low-market-residual-vol1m-pre2026-'
BASELINE_EVIDENCE_FILES = frozenset(BASELINE_PREFIX+tail+'.json' for tail in (
    'development-plan', 'development-results', 'development-independent-audit', 'cash-drag-attribution'))


def verify_baseline(repo, baseline, plan):
    """Authenticate all old financial bytes without loading pickle or replaying."""
    expected = {f'{cost}/{family}' for cost in EXTRA_BPS
                for family in ('eligible_equal_weight', CONTROL, *FAMILIES)}
    artifacts = {'report.pkl', 'positions.pkl', 'days.csv', 'orders.csv',
                 'holdings.csv', 'decision_intents.json', 'suspension_mark_audit.json'}
    if set(plan['baseline_evidence_sha256']) != BASELINE_EVIDENCE_FILES:
        raise ValueError('all four fixed baseline evidence bindings required')
    for name, checksum in plan['baseline_evidence_sha256'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or sha256_file(repo/path) != checksum:
            raise ValueError('frozen baseline evidence changed')
    if sha256_file(baseline/'summary.json') != plan['baseline_summary_sha256']:
        raise ValueError('old completed account summary changed')
    summary = json.loads((baseline/'summary.json').read_bytes())
    public = json.loads((repo/(BASELINE_PREFIX+'development-results.json')).read_bytes())
    audit_path = repo/(BASELINE_PREFIX+'development-independent-audit.json')
    audit = json.loads(audit_path.read_bytes())
    old_plan_sha = sha256_file(repo/(BASELINE_PREFIX+'development-plan.json'))
    if (public['actual_summary_sha256'] != plan['baseline_summary_sha256']
            or audit['summary_sha256'] != plan['baseline_summary_sha256']
            or public['independent_audit_sha256'] != sha256_file(audit_path)
            or any(obj['plan_sha256'] != old_plan_sha for obj in (summary, public, audit))):
        raise ValueError('original account summary and independent audit must share frozen anchors')
    results = summary['results_by_extra_bps_and_family']
    if set(results) != expected:
        raise ValueError('all six baseline cases must remain present')
    count = 0
    for label, row in results.items():
        if set(row['artifact_sha256']) != artifacts:
            raise ValueError('all seven baseline financial artifacts required')
        for name, checksum in row['artifact_sha256'].items():
            if sha256_file(baseline/label/name) != checksum:
                raise ValueError('original financial artifact changed')
            count += 1
    return count


def summarize_report(report,initial_cash):
    import pandas as pd
    net=report['return']-report['cost'];compound=float((1+net).prod()-1)
    expected=float(initial_cash)*(1+net).cumprod()
    if any(not math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=.01)
           for a,b in zip(expected,report['account'])):
        raise ValueError('daily net-return/account conservation failed')
    nav=pd.concat([pd.Series([float(initial_cash)]),report['account'].reset_index(drop=True)],ignore_index=True)
    return {'sessions':len(report),'net_compound_return_pct':compound*100,
        '2024_return_pct':float(((1+net.loc['2024']).prod()-1)*100),
        '2025_return_pct':float(((1+net.loc['2025']).prod()-1)*100),
        'average_exposure_pct':float((report['value']/report['account']).mean()*100),
        'max_drawdown_pct':float((nav/nav.cummax()-1).min()*100),
        'cost_pct_initial':float(report['total_cost'].iloc[-1]/initial_cash*100),
        'turnover_x_initial':float(report['total_turnover'].iloc[-1]/initial_cash)}


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('provider-uri','gap-states','plan','expected-plan-sha256','output-dir'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument("--source-preflight-only",action="store_true")
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
    if out.exists() or out.name!='low-market-residual-vol1m-budgeted-pre2026-development-20261021':raise ValueError('fixed new development output required')
    if sha256_file(args.plan)!=args.expected_plan_sha256:raise ValueError('registered development plan changed')
    plan=json.loads(Path(args.plan).read_text())
    if (plan['status']!='FROZEN_LOW_MARKET_RESIDUAL_VOL1M_BUDGETED_BEFORE_OUTCOMES' or plan['families']!=list(FAMILIES)
            or plan['extra_bps']!=list(EXTRA_BPS) or plan['capital_CNY']!=CAPITAL
            or plan['window']!=[START,END] or plan['candidate_budget']!=1
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(root/name)!=value for name,value in plan['method_code_sha256'].items())):
        raise ValueError('registered development rules changed')
    if sha256_file(root/'docs/research/low-market-residual-vol1m-budgeted-design-2026-10-21.md')!=plan['design_sha256']:
        raise ValueError('registered research design changed')
    baseline=out.parent/'low-market-residual-vol1m-pre2026-development-20261021'
    verify_baseline(root,baseline,plan)
    memberships=parse_memberships((Path(args.provider_uri)/'instruments/csi500.txt').read_text())
    if input_hashes(args.provider_uri,memberships)!=plan['input_sha256']:raise ValueError('frozen price snapshot changed')
    if sha256_file(Path(args.provider_uri)/'features/sh000905/close.day.bin')!=plan['market_close_sha256']:
        raise ValueError('market regression index source changed')
    states=load_state_capture(args.gap_states,plan['gap_state_manifest_sha256'])
    provider=Path(args.provider_uri)
    if sha256_file(provider/"manifest.json")!=plan["provider_manifest_sha256"]:
        raise ValueError("physical pre2026 provider identity changed")
    manifest=json.loads((provider/"manifest.json").read_text())
    snapshot=QlibSnapshot(args.provider_uri)
    if snapshot.calendar[-1].isoformat()!=END or manifest["all_output_values_at_or_before"]!=END:
        raise ValueError("provider must be physically capped at2025")
    future = provider/'calendars/day_future.txt'
    if sha256_file(future) != plan['future_calendar_sha256']:
        raise ValueError('fixed clock-only next-session boundary changed')
    expected_future = [day.isoformat() for day in snapshot.calendar]+[plan['clock_only_next_session']]
    if (future.read_text().splitlines() != expected_future
            or manifest['clock_boundary']['session'] != plan['clock_only_next_session']
            or manifest['clock_boundary']['additional_quote_values'] != 0
            or any(sha256_file(provider/name) != meta['sha256'] for name,meta in manifest['per_feature'].items())):
        raise ValueError('clock repair must preserve all pre2026 quotes')
    targets,receipts=build_targets(snapshot,memberships)
    if len(receipts)!=24 or any(row['latest_factor_price_read']!=row['formation_asof'] or row['formation_asof']>=row['execution_session'] for row in receipts):
        raise ValueError('development formation/time coverage incomplete')
    if any(hashlib.sha256((json.dumps(value,indent=2)+'\n').encode()).hexdigest()!=plan[key]
            for value,key in ((targets,'initial_targets_sha256'),(receipts,'initial_receipts_sha256'))):
        raise ValueError('frozen formation objects not reproduced')
    if args.source_preflight_only:
        print("24 frozen monthly residual-vol formations reproduced; physical data end2025; no account ROI",flush=True);return 0
    out.mkdir(parents=True)
    for name,value in (('targets.json',targets),('formation_receipts.json',receipts)):
        (out/name).write_text(json.dumps(value,indent=2)+'\n')
    if (sha256_file(out/'targets.json')!=plan['initial_targets_sha256']
            or sha256_file(out/'formation_receipts.json')!=plan['initial_receipts_sha256']):
        raise ValueError('frozen formation evidence changed')
    import pandas as pd
    import qlib
    from qlib.backtest import backtest
    from qlib.constant import REG_CN
    from stock_rsi.budgeted_qlib_strategy import BudgetedMonthlyPriorCloseStrategy
    qlib.init(provider_uri=args.provider_uri,region=REG_CN,kernels=1,logging_level=30)
    calendar=tuple(day for day in snapshot.calendar if day.isoformat()<=END)
    expected=pd.DatetimeIndex([day for day in calendar if START<=day.isoformat()<=END]);results={}
    for extra in EXTRA_BPS:
        for name in ('eligible_equal_weight',CONTROL,*FAMILIES):
            label=f'{extra}/{name}';folder=out/label;folder.mkdir(parents=True)
            print('budgeted market residual volatility development '+label,flush=True)
            strategy=BudgetedMonthlyPriorCloseStrategy(targets=targets[name],snapshot=snapshot)
            codes=sorted({code for target in targets[name].values() for code in target['weights']})
            portfolio,indicators=backtest(start_time=START,end_time=END,strategy=strategy,
                executor={'class':'SimulatorExecutor','module_path':'qlib.backtest.executor',
                    'kwargs':{'time_per_step':'day','generate_portfolio_metrics':True}},
                benchmark='SH000905',account=CAPITAL,
                exchange_kwargs={'freq':'day','codes':codes,'start_time':'2023-12-29','end_time':END,
                    'limit_threshold':OPEN_LIMITS,'deal_price':'open','open_cost':.0005+extra/10000,
                    'close_cost':.0015+extra/10000,'min_cost':5})
            report,positions=portfolio['1day']
            if (not report.index.equals(expected) or len(strategy.intents)!=24
                    or strategy.decision_days!=[day.strftime('%Y-%m-%d') for day in expected]):
                raise ValueError('account and monthly decision coverage incomplete')
            for intention in strategy.intents:
                prior=date.fromisoformat(intention['as_of_close_convention'][:10])
                equity=float(report.loc[pd.Timestamp(prior),'account']) if prior.isoformat()>=START else CAPITAL
                held=positions[pd.Timestamp(prior)].get_stock_amount_dict() if prior.isoformat()>=START else {}
                actual=intention['holdings_at_decision']
                if (not math.isclose(intention['equity_at_decision'],equity,rel_tol=1e-10,abs_tol=.01)
                        or set(actual)!=set(held) or any(not math.isclose(actual[c],float(q),rel_tol=1e-10,abs_tol=1e-8) for c,q in held.items())):
                    raise ValueError('order sizing crossed prior-close account boundary')
            evidence=reconcile_daily_evidence(report,positions,indicators['1day'][1].order_indicator_his,calendar,
                initial_cash=CAPITAL,signal_days={date.fromisoformat(t['as_of']) for t in targets[name].values()})
            marks=[]
            for row in evidence['holdings']:
                quote=snapshot.value(row['instrument'],'close',row['session'])
                if quote is None or quote<=0:
                    marks.append(verify_suspension_mark(snapshot,row['instrument'],row['session'],
                        row['normalized_price'],states.get(row['instrument'],{})))
            report.to_pickle(folder/'report.pkl');pd.to_pickle(positions,folder/'positions.pkl')
            for key in ('days','orders','holdings'):pd.DataFrame(evidence[key]).to_csv(folder/(key+'.csv'),index=False)
            (folder/'decision_intents.json').write_text(json.dumps(strategy.intents,indent=2)+'\n')
            (folder/'suspension_mark_audit.json').write_text(json.dumps(marks,indent=2)+'\n')
            results[label]={'status':'DAILY_PROXY_DEVELOPMENT_RECONCILED',**summarize_report(report,CAPITAL),
                'unverified_held_marks':sum(not row['verified'] for row in marks),'orders':len(evidence['orders']),
                'unfilled_orders':sum(row['fill_status']=='UNFILLED' for row in evidence['orders']),
                'artifact_sha256':{p.name:sha256_file(p) for p in sorted(folder.iterdir())}}
    verify_baseline(root,baseline,plan)
    if (sha256_file(args.plan)!=args.expected_plan_sha256
            or input_hashes(provider,memberships)!=plan['input_sha256']
            or sha256_file(provider/'manifest.json')!=plan['provider_manifest_sha256']
            or any(sha256_file(root/name)!=value for name,value in plan['method_code_sha256'].items())
            or any(sha256_file(provider/name)!=meta['sha256'] for name,meta in manifest['per_feature'].items())):
        raise ValueError('source/method or request changed during account replay')
    load_state_capture(args.gap_states,plan['gap_state_manifest_sha256'])
    selected=choose_development_lead({name:results['40/'+name] for name in FAMILIES})
    summary={'status':'LOW_MARKET_RESIDUAL_VOL1M_BUDGETED_PRE2026_DEVELOPMENT_COMPLETE','candidate_budget':len(FAMILIES),'economic_family':'EXISTING_LOW_RISK_LOTTERY_VARIANT','new_independent_economic_family':False,
        'start':START,'end':END,'results_by_extra_bps_and_family':results,'selected_development_lead':selected,
        'selection_rule':'At 40bp profile: both years positive, exposure>=90%, no unverified marks; maximize worse year, lower turnover tie-break.',
        'formation_receipts_sha256':sha256_file(out/'formation_receipts.json'),'targets_sha256':sha256_file(out/'targets.json'),
        'plan_sha256':args.expected_plan_sha256,'method_code_sha256':plan['method_code_sha256'],
        '2026_market_values_queried':False,'sealed_evidence':False,'objective_achieved':False,
        'claim_status':'NORMALIZED_DAILY_OPEN_ENGINEERING_SCREEN_REQUIRES_RAW_SHARE_INTRADAY_CONFIRMATION',
        'cost_definition':'Qlib max(5 CNY, gross*(base+extra)); differs from separately rounded per-child extra cost in intraday confirmation',
        'raw_share_execution_verified':False,'historical_arrival_verified':False,
        'clock_only_next_session':plan['clock_only_next_session'],
        'future_calendar_sha256':plan['future_calendar_sha256'],
        'allocation_trial_id':'low_market_residual_vol_1m_budgeted_lots',
        'allocation_policy':'EXISTING_SINGLE_DEFICIT_FLOOR_POSITIVE_SQUARED_ERROR_GREEDY_WITHIN_FIXED_BUDGET',
        'baseline_summary_sha256':plan['baseline_summary_sha256'],'all42_baseline_financial_bytes_unchanged':True,
        'physical_provider_end':'2025-12-31','provider_manifest_sha256':plan['provider_manifest_sha256']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('development screen complete; lead',selected,flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
