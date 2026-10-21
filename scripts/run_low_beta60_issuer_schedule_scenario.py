"""Six separately labelled conditional accounts; replay never scores aggregate ROI."""
import argparse
from decimal import Decimal
from functools import partial
import json
from pathlib import Path
from scripts import run_low_beta60_horizon_account as original
from scripts.run_low_beta60_horizon_account import SourceIOGuard, PARTICIPATION, EXTRA_BPS, CAPITAL, END, ARTIFACTS, IntradayBroker, simulate_fixed_targets, verify_financial_prefix, clean, write_case, file_sha
from stock_rsi.issuer_schedule_account import IssuerScheduleAccount, load_schedule_evidence

OUTPUT = 'low-beta60-issuer-schedule-account-20261021'
PRIOR_PLAN = 'experiments/qlib/low-beta60-horizon-account-plan.json'
REGISTRY = 'experiments/qlib/low-beta60-issuer-schedule-scenario.json'
BINDING_SCOPES = {
    'extra_method_sha256': ('scripts/run_low_beta60_issuer_schedule_scenario.py','src/stock_rsi/issuer_schedule_account.py','scripts/score_low_beta60_issuer_schedule_scenario.py'),
    'extra_public_sha256': (PRIOR_PLAN, REGISTRY,'docs/research/low-beta60-issuer-schedule-scenario-2026-10-21.md',
        'experiments/qlib/low-beta60-issuer-schedule-proposal-review.json'),
    'extra_local_sha256': ('low-beta60-intraday-horizon-20261021/summary.json',
        'low-beta60-intraday-horizon-20261021/case_results.json')}

def load_scenario(base,repo,plan):
    if any(set(plan[field]) != set(names) for field,names in BINDING_SCOPES.items()):
        raise ValueError('complete extra binding scope required')
    for field,names in BINDING_SCOPES.items():
        root = base if field == 'extra_local_sha256' else repo
        for name,h in plan[field].items():
            if file_sha(root/name) != h:raise ValueError('frozen extra method/source/evidence bytes changed')
    prior = json.loads((repo/PRIOR_PLAN).read_bytes())
    inputs = original.load_inputs(base,repo,prior)
    registry = json.loads((repo/REGISTRY).read_bytes())
    evidence = load_schedule_evidence(registry,base,repo,inputs[2])
    review = json.loads((repo/'experiments/qlib/low-beta60-issuer-schedule-proposal-review.json').read_bytes())
    if (review['approved'] is not True
            or review['proposal_sha256'] != file_sha(repo/REGISTRY)
            or review['protocol_doc_sha256'] != file_sha(repo/'docs/research/low-beta60-issuer-schedule-scenario-2026-10-21.md')):
        raise ValueError('independently approved exact scenario proposal required')
    failedroot = base/'low-beta60-intraday-horizon-20261021'
    failed = json.loads((failedroot/'summary.json').read_bytes())
    if failed['all_profiles_complete'] or failed['portfolio_returns_computed'] or len(failed['results_by_profile']) != 6:
        raise ValueError('preserved original six failures required')
    for label,result in failed['results_by_profile'].items():
        for name,h in result['failure_artifact_sha256'].items():
            if Path(name).name != name or file_sha(failedroot/label/name) != h:raise ValueError('preserved failure artifact changed')
    return (*inputs,evidence)

def run_profiles(out, calendar, bars, events, targets, bank, references, evidence):
    out = Path(out)
    if out.exists(): raise ValueError('preserve existing full or partial account replay')
    out.mkdir(parents=True); results = {}; bank = SourceIOGuard(bank)
    event_by_id = {e.event_id: e for e in events}
    for participation in PARTICIPATION:
        for cost in EXTRA_BPS:
            profile = f'{participation}/{cost}'; folder = out / profile; folder.mkdir(parents=True); holders = []
            print('continuous account', profile, 'initialCNY', CAPITAL, flush=True)
            def factory(cal, cash, distributions, **kwargs):
                broker = partial(IntradayBroker, participation_bps=participation, extra_cost_bps=cost, tape_provider=bank)
                account = IssuerScheduleAccount(cal, cash, distributions, schedule_evidence=evidence, broker_factory=broker, **kwargs)
                holders.append(account); return account
            try:
                case = simulate_fixed_targets(calendar, bars, events, targets, CAPITAL, lifecycles={}, account_factory=factory, policy_id='low_beta60')
                if len(case['days']) != 676 or len(case['intents']) != 34 or case['days'][-1]['day'] != END:
                    raise ValueError('complete676-session34-intent account required')
                for r in case['corporate_ledger']:
                    if r['kind'] != 'EX_DATE_ENTITLEMENT' or not r['registered_quantity']: continue
                    e = event_by_id[r['event_id']]
                    if (e.capital_per_share and not e.capital_tax_exempt_verified and not holders[0].supports_conditional_event(e)) or (e.stock_per_share and not e.stock_tax_basis_verified):
                        raise ValueError('owned noncash event has unsupported tax evidence')
                case['parent_instructions'] = case.pop('orders'); case['orders'] = holders[0].broker.child_orders
                verify_financial_prefix(case, references[profile])
                if case['whole_day_volume_violations']:
                    raise ValueError('whole-day source capacity exceeded')
                artifacts = write_case(folder, case)
                scenario = clean(holders[0].scenario_ledger)
                if len(scenario) != 1 or scenario[0]['registered_quantity'] <= 0:
                    raise ValueError('exactly one owned conditional use required')
                (folder/'scenario_ledger.json').write_text(json.dumps(scenario,indent=2)+'\n')
                artifacts['scenario_ledger.json'] = file_sha(folder/'scenario_ledger.json')
                result = {'status':'CONDITIONAL_ENGINEERING_ACCOUNT_COMPLETE_UNSCORED',
                    'development_financial_prefix_identical':True,'source_events_changed':False,
                    'statutory_exemption_verified':False,'account_sessions':len(case['days'])-1,
                    'monthly_decisions':len(case['intents']),'scenario_uses':len(scenario),
                    'portfolio_returns_computed':False,'artifact_sha256':artifacts}
            except (ValueError, KeyError, ArithmeticError, OSError) as exc:
                result = {'status': 'INVALID_SOURCE_OR_ACCOUNT', 'error_type': type(exc).__name__, 'error': str(exc), 'portfolio_returns_computed': False}
                if holders:
                    account = holders[0]
                    state = clean({'last_account_clock': account._last_clock, 'last_intraday_end': account.broker._last_end,
                        'cash': account.broker.cash, 'positions': account.broker.positions, 'owned_shares': account.owned_quantities(),
                        'entitlements': account.entitlements,'scenario_ledger':account.scenario_ledger, 'parent_instructions': account.broker.orders, 'child_orders': account.broker.child_orders,
                        'fills': account.broker.fills, 'corporate_ledger': account.corporate_ledger, 'cash_claims': account.cash_claims, 'stock_claims': account.stock_claims})
                    (folder / 'failed_account_state.json').write_text(json.dumps(state, indent=2) + '\n')
                (folder / 'error.json').write_text(json.dumps(result, indent=2) + '\n')
                result['failure_artifact_sha256'] = {f.name: file_sha(f) for f in sorted(folder.iterdir())}
            results[profile] = result
            (out / 'case_results.json').write_text(json.dumps(results, indent=2) + '\n')
    return results


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('plan','expected-plan-sha256','source-root','output-dir'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir)
    if out.exists() or file_sha(a.plan) != a.expected_plan_sha256:raise ValueError('frozen external plan and unused output required')
    plan=json.loads(Path(a.plan).read_bytes())
    if (plan['status'] != 'FROZEN_SIX_CONDITIONAL_ISSUER_SCHEDULE_ACCOUNTS_NO_ROI'
            or plan['output_directory'] != OUTPUT or out.resolve() != (base/OUTPUT).resolve()
            or plan['window'] != ['2023-12-29',END] or plan['initial_CNY'] != CAPITAL
            or plan['participation_bps'] != list(PARTICIPATION) or plan['extra_cost_bps'] != list(EXTRA_BPS)
            or plan['source_queries_allowed'] is not False or plan['investment_rule_changes_allowed'] is not False
            or plan['aggregate_ROI_in_replay_allowed'] is not False):raise ValueError('fixed conditional scenario protocol changed')
    inputs=load_scenario(base,repo,plan)
    results=run_profiles(out,*inputs)
    summary={'status':'SIX_CONDITIONAL_ENGINEERING_ACCOUNTS_RECORDED_UNSCORED','plan_sha256':a.expected_plan_sha256,
        'window':plan['window'],'initial_CNY':CAPITAL,'results_by_profile':results,
        'all_profiles_complete':all(r['status']=='CONDITIONAL_ENGINEERING_ACCOUNT_COMPLETE_UNSCORED' for r in results.values()),
        'scenario_classification':'ISSUER_FORMAL_TAX_SCHEDULE_COMPOSITE_INFERENCE',
        'statutory_exemption_verified':False,'source_events_changed':False,'source_queries':0,
        'portfolio_returns_computed':False,'full_October_complete':False,'sealed_evidence':False,
        'historical_arrival_verified':False,'queue_and_impact_calibrated':False,'actual_FIFO_tax_liability_verified':False,
        'candidate_promoted':False,'objective_achieved':False}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('conditional accounts complete',summary['all_profiles_complete'],'aggregate ROI computed',False,flush=True)
    return 0 if summary['all_profiles_complete'] else 2

if __name__=='__main__':raise SystemExit(main())
