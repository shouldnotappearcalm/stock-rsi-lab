"""Frozen Amihud22 development confirmation, all predeclared account profiles."""
import argparse
from dataclasses import asdict
from decimal import Decimal
from functools import partial
import json
from pathlib import Path

from scripts.capture_frozen_target_development_data import END
from scripts.admit_illiquidity_minutes_pre2026 import METHOD_FILES as ADMISSION_METHODS
from scripts.fundamental_query_journal import file_sha
from scripts.prepare_illiquidity_account_events import METHOD_FILES as SOURCE_METHODS,authenticate_sources,classify_source_coverage
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from scripts.run_low_risk_intraday_replay import METHOD_FILES as SHARED_METHODS,PARTICIPATION,EXTRA_BPS,TapeBank,write_case
from scripts.run_low_risk_raw_share_validation import CAPITALS,clean,summarize_case
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

METHOD_FILES=tuple(dict.fromkeys((*SHARED_METHODS,*SOURCE_METHODS,*ADMISSION_METHODS,
    'scripts/run_illiquidity_intraday_development.py','scripts/replay_stock_distribution_targets.py',
    'scripts/admit_illiquidity_minutes_pre2026.py','scripts/illiquidity_minute_sources.py')))


def confirmation_passes(results):
    import math
    for participation in PARTICIPATION:
        r=results.get(f'{participation}/40/1000000',{})
        if (r.get('status')!='NESTED_EXECUTION_ACCOUNT_RECONCILED'
                or r.get('zero_entitlements_verified') is not True or r.get('actual_delisting_exit_verified') is not True):return False
        values=[r.get(k,float('nan')) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct')]
        if not all(math.isfinite(v) for v in values) or min(values[:2])<=0 or values[2]<90:return False
    return True


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('raw-data-dir','proof-dir','targets','old-tape-dir','extra-tape-dir','source-events-dir',
                 'minute-admission','plan','expected-plan-sha256','output-dir'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
    if out.exists():raise ValueError('development confirmation output already exists')
    if file_sha(args.plan)!=args.expected_plan_sha256:raise ValueError('frozen development replay plan changed')
    plan=json.loads(Path(args.plan).read_text())
    if (plan['status']!='FROZEN_BEFORE_ILLIQUIDITY_INTRADAY_DEVELOPMENT_OUTCOMES'
            or plan['participation_bps']!=list(PARTICIPATION) or plan['extra_bps']!=list(EXTRA_BPS)
            or plan['capitals']!=list(CAPITALS) or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or any(file_sha(root/n)!=h for n,h in plan['method_code_sha256'].items())):
        raise ValueError('frozen complete account method or profile matrix changed')
    for name,key in (('experiments/qlib/illiquidity-pre2026-results.json','screen_summary_sha256'),
            ('experiments/qlib/illiquidity-pre2026-independent-csv-audit.json','screen_audit_sha256')):
        if file_sha(root/name)!=plan[key]:raise ValueError('daily development admission evidence changed')
    audit=json.loads((root/'experiments/qlib/illiquidity-pre2026-independent-csv-audit.json').read_text())
    if audit['development_gate_passes_independently'] is not True or audit['summary_sha256']!=plan['screen_summary_sha256']:
        raise ValueError('daily development admission not independently passed')
    raw,proofdir,old,extra,source=map(Path,(args.raw_data_dir,args.proof_dir,args.old_tape_dir,args.extra_tape_dir,args.source_events_dir))
    for path,key in ((raw/'manifest.json','raw_manifest_sha256'),(proofdir/'reviewed-manifest.json','proof_manifest_sha256'),
            (old/'manifest.json','old_tape_manifest_sha256'),(extra/'manifest.json','extra_tape_manifest_sha256'),
            (source/'summary.json','source_event_summary_sha256'),(Path(args.targets),'target_sha256'),
            (Path(args.minute_admission),'minute_admission_sha256')):
        if file_sha(path)!=plan[key]:raise ValueError('frozen development source identity changed')
    admission=json.loads(Path(args.minute_admission).read_text())
    if (set(admission['method_code_sha256'])!=set(ADMISSION_METHODS)
            or any(file_sha(root/n)!=h for n,h in admission['method_code_sha256'].items())
            or admission['admitted_for_reconstructed_execution'] is not True
            or any(admission[k]!=plan[k] for k in ('raw_manifest_sha256','proof_manifest_sha256','old_tape_manifest_sha256','extra_tape_manifest_sha256'))):
        raise ValueError('complete source admission absent or differs from account')
    packets,proof,calendar=authenticate_sources(raw,proofdir,Path(args.targets),root)
    events,receipts=compile_distribution_events(packets,proof,calendar);classify_source_coverage(packets,proof,calendar)
    source_summary=json.loads((source/'summary.json').read_text())
    for name,h in source_summary['artifact_sha256'].items():
        if Path(name).name!=name or file_sha(source/name)!=h:raise ValueError('source-event artifact changed')
    if (json.loads((source/'derived_events.json').read_text())!=clean([asdict(e) for e in events])
            or json.loads((source/'event_source_receipts.json').read_text())!=list(receipts)):
        raise ValueError('compiled original source events changed')
    bars={code:{r['date']:r for r in p['bars']} for code,p in packets.items()}
    targets=json.loads(Path(args.targets).read_text());bank=TapeBank(old,extra,bars,END)
    zero_ids={r['event_id'] for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']}
    out.mkdir(parents=True);results={}
    (out/'derived_events.json').write_text(json.dumps(clean([asdict(e) for e in events]),indent=2)+'\n')
    (out/'event_source_receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
    for participation in PARTICIPATION:
        for cost in EXTRA_BPS:
            for capital in CAPITALS:
                label=f'{participation}/{cost}/{capital}';folder=out/label;folder.mkdir(parents=True);holders=[]
                print('illiquidity intraday development '+label,flush=True)
                def factory(cal,cash,distributions,**kwargs):
                    constructor=partial(IntradayBroker,participation_bps=participation,extra_cost_bps=cost,tape_provider=bank)
                    account=StockDistributionAccount(cal,cash,distributions,broker_factory=constructor,**kwargs);holders.append(account);return account
                try:
                    case=simulate_fixed_targets(calendar,bars,events,targets,capital,lifecycles=proof['lifecycles'],account_factory=factory)
                    if len(case['intents'])!=24:raise ValueError('complete monthly decisions required')
                    record={r['event_id']:r['quantity'] for r in case['corporate_ledger'] if r['kind']=='RECORD_DATE_OWNERSHIP' and r['event_id'] in zero_ids}
                    ex={r['event_id']:r['registered_quantity'] for r in case['corporate_ledger'] if r['kind']=='EX_DATE_ENTITLEMENT' and r['event_id'] in zero_ids}
                    if set(record)!=zero_ids or set(ex)!=zero_ids or any(record[k]!=0 or ex[k]!=0 for k in zero_ids):
                        raise ValueError('unverified share distribution has actual entitlement')
                    case['parent_instructions']=case.pop('orders');case['orders']=holders[0].broker.child_orders
                    (folder/'lifecycle_source_audit.json').write_text(json.dumps(case['lifecycle_source_audit'],indent=2)+'\n')
                    artifacts=write_case(folder,case)
                    development_days=[r for r in case['days'] if r['day']>='2024-01-02']
                    results[label]={'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED',**summarize_case(case,capital),
                        'average_exposure_pct':float(sum((r['exposure'] for r in development_days),Decimal(0))/len(development_days)*100),
                        'zero_entitlements_verified':True,'actual_delisting_exit_verified':True,
                        'unfilled_parents':sum(p['remaining']>0 for p in case['parent_instructions']),
                        'artifact_sha256':artifacts}
                except (ValueError,KeyError) as exc:
                    results[label]={'status':'INVALID_SOURCE_OR_ACCOUNT','error':str(exc)}
                    if holders:
                        a=holders[0]
                        (folder/'failed_account_state.json').write_text(json.dumps(clean({
                            'cash':a.broker.cash,'positions':a.broker.positions,'owned_shares':a.owned_quantities(),
                            'parent_instructions':a.broker.orders,'child_orders':a.broker.child_orders,'fills':a.broker.fills,
                            'corporate_ledger':a.corporate_ledger,'cash_claims':a.cash_claims,'stock_claims':a.stock_claims}),indent=2)+'\n')
                    (folder/'error.json').write_text(json.dumps(results[label],indent=2)+'\n')
                    results[label]['failure_artifact_sha256']={p.name:file_sha(p) for p in sorted(folder.iterdir())}
                (out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
    result={'status':'ILLIQUIDITY_INTRADAY_DEVELOPMENT_COMPLETE','strategy':'amihud22','phase':'dev',
        'start':'2024-01-02','source_warmup_start':'2023-12-29','end':END,'results_by_profile':results,
        'method_code_sha256':plan['method_code_sha256'],'plan_sha256':args.expected_plan_sha256,
        'raw_development_confirmation_passes':confirmation_passes(results),'reference_CNY':'1000000',
        'confirmation_rule':'All three registered participation levels at40bp: both development years positive, exposure>=90%, actualzero unverifiedtax entitlements and actualdelistingflat.',
        'tape_accessed_sessions':len(bank.accessed),'derived_events_sha256':file_sha(out/'derived_events.json'),
        'event_source_receipts_sha256':file_sha(out/'event_source_receipts.json'),
        'source_evidence_level':'RECONSTRUCTED_ENGINEERING_SIMULATION','queue_and_impact_calibrated':False,
        'historical_arrival_verified':False,'2026_strategy_returns_queried':False,'sealed_evidence':False,'objective_achieved':False}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print('illiquidity development complete',result['raw_development_confirmation_passes'],flush=True)


if __name__=='__main__':main()
