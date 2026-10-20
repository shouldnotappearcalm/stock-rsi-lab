"""Frozen budgeted-lot market-residual-momentum-hypothesis development screen, with no 2026 market queries.

Qlib normalized inventory and daily-open execution are screening proxies.
Any retained lead must separately pass raw-share intraday account replay.
"""
import argparse
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
from stock_rsi.market_residual_momentum import CONTROL, FAMILIES, START, END, build_targets, choose_development_lead
from stock_rsi.suspension_evidence import verify_suspension_mark


CAPITAL=1000000
EXTRA_BPS=(20,40)
METHOD_FILES=tuple(dict.fromkeys((*SHARED_FILES,'scripts/run_cninfo_orj_signal_pre2026.py',
    'scripts/prepare_qlib_master_market_pre2026.py','scripts/run_qlib_budgeted_residual_pre2026.py',
    'src/stock_rsi/return_families.py','src/stock_rsi/market_residual_momentum.py',
    'src/stock_rsi/budgeted_lot_orders.py','src/stock_rsi/budgeted_qlib_strategy.py')))


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
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
    if out.exists():raise ValueError('development output already exists')
    if sha256_file(args.plan)!=args.expected_plan_sha256:raise ValueError('registered development plan changed')
    plan=json.loads(Path(args.plan).read_text())
    if (plan['status']!='FROZEN_BEFORE_BUDGETED_RESIDUAL_OUTCOMES' or plan['families']!=list(FAMILIES)
            or plan['extra_bps']!=list(EXTRA_BPS) or plan['capital_CNY']!=CAPITAL
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(root/name)!=value for name,value in plan['method_code_sha256'].items())):
        raise ValueError('registered development rules changed')
    if (sha256_file(root/plan['baseline_plan_file'])!=plan['baseline_plan_sha256']
            or sha256_file(root/plan['baseline_summary_file'])!=plan['baseline_summary_sha256']):
        raise ValueError('original baseline evidence changed')
    memberships=parse_memberships((Path(args.provider_uri)/'instruments/csi500.txt').read_text())
    if input_hashes(args.provider_uri,memberships)!=plan['input_sha256']:raise ValueError('frozen price snapshot changed')
    if sha256_file(Path(args.provider_uri)/'features/sh000905/close.day.bin')!=plan['market_close_sha256']:
        raise ValueError('market regression index source changed')
    states=load_state_capture(args.gap_states,plan['gap_state_manifest_sha256'])
    snapshot=QlibSnapshot(args.provider_uri);targets,receipts=build_targets(snapshot,memberships)
    if len(receipts)!=24 or any(row['latest_factor_price_read']!=row['formation_asof'] for row in receipts):
        raise ValueError('development formation/time coverage incomplete')
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
            print('budgeted residual development '+label,flush=True)
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
    selected=choose_development_lead({name:results['40/'+name] for name in FAMILIES})
    summary={'status':'BUDGETED_RESIDUAL_PRE2026_DEVELOPMENT_COMPLETE','candidate_budget':len(FAMILIES),
        'start':START,'end':END,'results_by_extra_bps_and_family':results,'selected_development_lead':selected,
        'selection_rule':'At 40bp profile: both years positive, exposure>=90%, no unverified marks; maximize worse year, lower turnover tie-break.',
        'formation_receipts_sha256':sha256_file(out/'formation_receipts.json'),'targets_sha256':sha256_file(out/'targets.json'),
        'plan_sha256':args.expected_plan_sha256,'method_code_sha256':plan['method_code_sha256'],
        '2026_market_values_queried':False,'sealed_evidence':False,'objective_achieved':False,
        'claim_status':'NORMALIZED_DAILY_OPEN_ENGINEERING_SCREEN_REQUIRES_RAW_SHARE_INTRADAY_CONFIRMATION',
        'cost_definition':'Qlib max(5 CNY, gross*(base+extra)); differs from separately rounded per-child extra cost in intraday confirmation',
        'raw_share_execution_verified':False,'historical_arrival_verified':False,
        'allocation_policy':'SINGLE_DEFICIT_FLOOR_THEN_POSITIVE_SQUARED_ERROR_GREEDY_WITHIN_TARGET_NOTIONAL',
        'baseline_plan_sha256':plan['baseline_plan_sha256'],
        'baseline_summary_sha256':plan['baseline_summary_sha256']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('development screen complete; lead',selected,flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
