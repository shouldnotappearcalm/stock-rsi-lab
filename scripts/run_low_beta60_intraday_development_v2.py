"""V2 source-IO failure retention; frozen V1 economics and source code unchanged."""
import argparse,json
from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path
from scripts.run_low_beta60_intraday_development import METHOD_FILES as ORIGINAL_METHODS,PARTICIPATION,EXTRA_BPS,CAPITAL,END,load_inputs,confirmation_passes
from scripts.fundamental_query_journal import file_sha
from scripts.run_low_risk_intraday_replay import write_case
from scripts.run_low_risk_raw_share_validation import clean,summarize_case
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

METHOD_FILES=tuple((*ORIGINAL_METHODS,'scripts/run_low_beta60_intraday_development_v2.py'))


class SourceIOGuard:
    def __init__(self,bank):self.bank=bank;self.index=bank.index;self.accessed=bank.accessed
    def __call__(self,code,day):
        try:return self.bank(code,day)
        except OSError as exc:raise ValueError('frozen minute source IO failure: '+str(exc)) from exc


def run_profiles(out,calendar,bars,events,targets,bank):
    out=Path(out)
    if out.exists():raise ValueError('preserve previous complete or partial profile attempt')
    out.mkdir(parents=True);results={};bank=SourceIOGuard(bank);event_by_id={e.event_id:e for e in events}
    for participation in PARTICIPATION:
        for cost in EXTRA_BPS:
            label=f'{participation}/{cost}';folder=out/label;folder.mkdir(parents=True);holders=[]
            print('lowbeta intraday development',label,'CNY',CAPITAL,flush=True)
            def factory(cal,cash,distributions,**kwargs):
                broker=partial(IntradayBroker,participation_bps=participation,extra_cost_bps=cost,tape_provider=bank)
                account=StockDistributionAccount(cal,cash,distributions,broker_factory=broker,**kwargs);holders.append(account);return account
            try:
                case=simulate_fixed_targets(calendar,bars,events,targets,CAPITAL,lifecycles={},account_factory=factory,policy_id='low_beta60')
                days=[r for r in case['days'] if r['day']>='2024-01-02']
                if len(case['intents'])!=24 or len(days)!=485 or len(case['days'])!=486:raise ValueError('complete continuous development account required')
                for item in case['corporate_ledger']:
                    if item['kind']!='EX_DATE_ENTITLEMENT' or not item['registered_quantity']:continue
                    e=event_by_id[item['event_id']]
                    if e.capital_per_share and not e.capital_tax_exempt_verified or e.stock_per_share and not e.stock_tax_basis_verified:
                        raise ValueError('owned noncash entitlement lacks supported tax evidence')
                case['parent_instructions']=case.pop('orders');case['orders']=holders[0].broker.child_orders
                artifacts=write_case(folder,case);peak=Decimal(CAPITAL);dd=Decimal(0)
                for row in days:peak=max(peak,row['equity']);dd=min(dd,row['equity']/peak-1)
                result={'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED' if case['whole_day_volume_violations']==0 else 'INVALID_WHOLE_DAY_CAPACITY',
                    **summarize_case(case,CAPITAL),'account_sessions':len(days),
                    'average_exposure_pct':float(sum((r['exposure'] for r in days),Decimal(0))/len(days)*100),
                    'max_drawdown_pct':float(dd*100),'noncash_entitlements_supported':True,
                    'parent_instructions':len(case['parent_instructions']),'child_orders':len(case['orders']),
                    'unfilled_parents':sum(p['remaining']>0 for p in case['parent_instructions']),
                    'all_children_within_1million_shares':all(0<o['quantity']<=1000000 for o in case['orders']),
                    'artifact_sha256':artifacts}
            except (ValueError,KeyError,ArithmeticError,OSError) as exc:
                result={'status':'INVALID_SOURCE_OR_ACCOUNT','error_type':type(exc).__name__,'error':str(exc)}
                if holders:
                    account=holders[0];state=clean({'last_account_clock':account._last_clock,'last_intraday_end':account.broker._last_end,
                        'cash':account.broker.cash,'positions':account.broker.positions,'owned_shares':account.owned_quantities(),
                        'parent_instructions':account.broker.orders,'child_orders':account.broker.child_orders,'fills':account.broker.fills,
                        'corporate_ledger':account.corporate_ledger,'cash_claims':account.cash_claims,'stock_claims':account.stock_claims})
                    (folder/'failed_account_state.json').write_text(json.dumps(state,indent=2)+'\n')
                (folder/'error.json').write_text(json.dumps(result,indent=2)+'\n')
                result['failure_artifact_sha256']={p.name:file_sha(p) for p in sorted(folder.iterdir())}
            results[label]=result;(out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
    return results


def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('source-root','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+name,required=True)
    a=p.parse_args(argv);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
    if out.exists():raise ValueError('preserve prior V2 parity replay')
    if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('frozen V2 parity plan changed')
    plan=json.loads(Path(a.plan).read_text())
    if (plan['status']!='FROZEN_LOW_BETA60_INTRADAY_V2_LEDGER_PARITY'
            or plan['participation_bps']!=list(PARTICIPATION) or plan['extra_cost_bps']!=list(EXTRA_BPS)
            or plan['initial_CNY']!=CAPITAL or plan['window']!=['2023-12-29',END]
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or plan['original_plan_sha256']!='fff4f3f26f0dd5e99f99d63cd0c77f899e8397e098a9e59a4b298f3e234fc8c0'):
        raise ValueError('V2 source handling cannot change frozen investment or profiles')
    calendar,bars,events,receipts,targets,bank=load_inputs(base,repo,plan)
    original_dir=base/'low-beta60-intraday-development-20261021'
    if file_sha(original_dir/'summary.json')!=plan['original_run_summary_sha256']:raise ValueError('original diagnostic identity changed')
    original=json.loads((original_dir/'summary.json').read_text())
    if original['plan_sha256']!=plan['original_plan_sha256']:raise ValueError('original account plan changed')
    for profile,r in original['results_by_profile'].items():
        for name,h in r['artifact_sha256'].items():
            if Path(name).name!=name or file_sha(original_dir/profile/name)!=h:raise ValueError('original accounting evidence changed')
    results=run_profiles(out,calendar,bars,events,targets,bank)
    (out/'derived_events.json').write_text(json.dumps(clean([asdict(e) for e in events]),indent=2)+'\n')
    (out/'event_source_receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
    parity={profile:results[profile].get('artifact_sha256')==r['artifact_sha256'] for profile,r in original['results_by_profile'].items()}
    summary={**original,'status':'LOW_BETA60_INTRADAY_V2_SOURCE_IO_GUARD_PARITY_COMPLETE',
        'method_code_sha256':plan['method_code_sha256'],'plan_sha256':a.expected_plan_sha256,
        'original_plan_sha256':plan['original_plan_sha256'],'original_run_summary_sha256':plan['original_run_summary_sha256'],
        'results_by_profile':results,'raw_development_confirmation_passes':confirmation_passes(results),
        'all_42_accounting_files_byte_identical_to_original':all(parity.values()),'parity_by_profile':parity,
        'tape_accessed_pairs':len(bank.accessed),'source_prefix_pairs':len(bank.index),
        'derived_events_sha256':file_sha(out/'derived_events.json'),'event_source_receipts_sha256':file_sha(out/'event_source_receipts.json'),
        'all_profiles_independently_audited':False,'2026_strategy_returns_queried':False,'candidate_promoted':False,'objective_achieved':False}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('V2 original ledger byte parity',all(parity.values()),flush=True)
    return 0 if all(parity.values()) else 2


if __name__=='__main__':raise SystemExit(main())
