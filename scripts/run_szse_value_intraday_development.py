"""Confirm a frozen development lead with the existing raw intraday executor."""
import argparse
import json
from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
from scripts.capture_frozen_target_development_data import START,END,target_codes
from scripts.return_family_development_inputs import prepare_events
from scripts.run_low_risk_intraday_replay import (
    METHOD_FILES as SHARED_METHOD_FILES,PARTICIPATION,EXTRA_BPS,TapeBank,write_case,
)
from scripts.run_low_risk_raw_share_validation import CAPITALS,clean,simulate_fixed_targets,summarize_case,validate_source_coverage
from scripts.run_reversal_intraday_development import confirmation_passes
from stock_rsi.calendar import TradingCalendar
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.raw_share_account import RawShareAccount


METHOD_FILES=tuple(dict.fromkeys((*SHARED_METHOD_FILES,'scripts/run_szse_value_intraday_development.py',
    'scripts/return_family_development_inputs.py','scripts/capture_frozen_target_development_data.py',
    'src/stock_rsi/return_families.py','src/stock_rsi/prior_close_orders.py',
    'scripts/run_reversal_intraday_development.py','src/stock_rsi/exchange_value.py','src/stock_rsi/szse_monthly.py')))


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('raw-data-dir','proof-dir','targets','old-tape-dir','extra-tape-dir','plan','expected-plan-sha256','output-dir'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
    if out.exists():raise ValueError('development confirmation output already exists')
    if sha256_file(args.plan)!=args.expected_plan_sha256:raise ValueError('development confirmation plan changed')
    plan=json.loads(Path(args.plan).read_text())
    if (plan['status']!='FROZEN_BEFORE_SZSE_VALUE_INTRADAY_DEV_OUTCOMES' or plan['participation_bps']!=list(PARTICIPATION)
            or plan['extra_bps']!=list(EXTRA_BPS) or plan['capitals']!=list(CAPITALS)
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(root/name)!=value for name,value in plan['method_code_sha256'].items())):
        raise ValueError('frozen confirmation method changed')
    for name,key in (('experiments/qlib/szse-value-pre2026-results.json','screen_summary_sha256'),
                     ('experiments/qlib/szse-value-pre2026-independent-csv-audit.json','screen_audit_sha256'),
                     ('experiments/qlib/szse-value-development-minute-admission.json','minute_admission_sha256')):
        if sha256_file(root/name)!=plan[key]:raise ValueError('development admission evidence changed')
    screen=json.loads((root/'experiments/qlib/szse-value-pre2026-results.json').read_text())
    audit=json.loads((root/'experiments/qlib/szse-value-pre2026-independent-csv-audit.json').read_text())
    admission=json.loads((root/'experiments/qlib/szse-value-development-minute-admission.json').read_text())
    if (screen['selected_development_lead']!='szse_monthly_low_pe'
            or audit['development_gate_passes_independently'] is not True
            or admission['admitted_for_reconstructed_execution'] is not True
            or any(admission[k]!=plan[k] for k in ('raw_manifest_sha256','old_tape_manifest_sha256','extra_tape_manifest_sha256'))
            or audit['summary_sha256']!=plan['screen_summary_sha256']):
        raise ValueError('pre2026 screen or source admission not passed')
    raw,proofdir,old,extra=map(Path,(args.raw_data_dir,args.proof_dir,args.old_tape_dir,args.extra_tape_dir))
    if (sha256_file(raw/'manifest.json')!=plan['raw_manifest_sha256']
            or sha256_file(proofdir/'reviewed-manifest.json')!=plan['proof_manifest_sha256']
            or sha256_file(args.targets)!=plan['target_sha256']
            or sha256_file(old/'manifest.json')!=plan['old_tape_manifest_sha256']
            or sha256_file(extra/'manifest.json')!=plan['extra_tape_manifest_sha256']):raise ValueError('confirmation source identity changed')
    manifest=json.loads((raw/'manifest.json').read_text());proof=json.loads((proofdir/'reviewed-manifest.json').read_text())
    if (proof['raw_manifest_sha256']!=plan['raw_manifest_sha256'] or proof['target_sha256']!=plan['target_sha256']
            or sha256_file(proofdir/'manifest.json')!=proof['capture_manifest_sha256']
            or sha256_file(raw/'calendar.json')!=manifest['calendar_sha256']):raise ValueError('source provenance or calendar changed')
    for document in proof['documents']:
        name=document['file']
        if Path(name).name!=name or document['day']>END or sha256_file(proofdir/name)!=document['sha256']:
            raise ValueError('primary corporate source changed')
    document_map={d['file']:d for d in proof['documents']}
    if (len(document_map)!=len(proof['documents']) or any(
            document_map.get(s['source_file'],{}).get('sha256')!=s['source_sha256']
            or document_map[s['source_file']]['instrument']!=s['instrument']
            or document_map[s['source_file']]['day']!=s['record']['dividPlanDate']
            for s in proof['supplementary_distributions'])):
        raise ValueError('supplement does not reference an authenticated notice')
    sessions=json.loads((raw/'calendar.json').read_text())['sessions']
    if sessions[0]!=START or sessions[-1]!=END or sessions!=sorted(set(sessions)):raise ValueError('complete development calendar required')
    calendar=TradingCalendar(sessions);targets=json.loads(Path(args.targets).read_text());codes=target_codes(targets)
    if set(codes)!=set(manifest['per_code_sha256']):raise ValueError('complete frozen target universe required')
    packets={}
    for code in codes:
        path=raw/'codes'/(code+'.json')
        if sha256_file(path)!=manifest['per_code_sha256'][code]:raise ValueError('raw corporate/price packet changed')
        packet=json.loads(path.read_text())
        if (packet['instrument']!=code or packet['window']!=[START,END]
                or [r['date'] for r in packet['bars']]!=sessions):raise ValueError('raw development identity/coverage changed')
        packets[code]=packet
    merged,events,zero=prepare_events(packets,targets,proof);validate_source_coverage(merged)
    bars={code:{r['date']:r for r in packet['bars']} for code,packet in merged.items()}
    bank=TapeBank(old,extra,bars,END);out.mkdir(parents=True);results={}
    (out/'derived_events.json').write_text(json.dumps(clean([asdict(e) for e in events]),indent=2)+'\n')
    (out/'zero_entitlement_proofs.json').write_text(json.dumps(zero,indent=2)+'\n')
    for participation in PARTICIPATION:
        for cost in EXTRA_BPS:
            for capital in CAPITALS:
                label=f'{participation}/{cost}/{capital}';folder=out/label;folder.mkdir(parents=True);holders=[]
                print('exchange value intraday development '+label,flush=True)
                def factory(cal,cash,distributions,**kwargs):
                    constructor=partial(IntradayBroker,participation_bps=participation,extra_cost_bps=cost,tape_provider=bank)
                    account=RawShareAccount(cal,cash,distributions,broker_factory=constructor,**kwargs);holders.append(account.broker);return account
                try:
                    case=simulate_fixed_targets(calendar,bars,events,targets,capital,account_factory=factory)
                    if len(case['intents'])!=24:raise ValueError('complete monthly decisions required')
                    zero_ids={r['event_id'] for r in zero}
                    record={r['event_id']:r['quantity'] for r in case['corporate_ledger'] if r['kind']=='RECORD_DATE_OWNERSHIP' and r['event_id'] in zero_ids}
                    ex={r['event_id']:r['registered_quantity'] for r in case['corporate_ledger'] if r['kind']=='EX_DATE_ENTITLEMENT' and r['event_id'] in zero_ids}
                    if set(record)!=zero_ids or set(ex)!=zero_ids or any(record[k]!=0 or ex[k]!=0 for k in zero_ids):
                        raise ValueError('unsupported share distribution has actual entitlement')
                    case['parent_instructions']=case.pop('orders');case['orders']=holders[0].child_orders
                    artifacts=write_case(folder,case)
                    development_days=[r for r in case['days'] if r['day']>='2024-01-02']
                    results[label]={'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED',**summarize_case(case,capital),
                        'average_exposure_pct':float(sum((r['exposure'] for r in development_days),Decimal(0))/len(development_days)*100),
                        'zero_entitlements_verified':True,'unfilled_parents':sum(p['remaining']>0 for p in case['parent_instructions']),
                        'artifact_sha256':artifacts}
                except (ValueError,KeyError) as exc:
                    results[label]={'status':'INVALID_SOURCE_OR_ACCOUNT','error':str(exc)}
                    (folder/'error.json').write_text(json.dumps(results[label],indent=2)+'\n')
                (out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
    result={'status':'SZSE_VALUE_INTRADAY_DEVELOPMENT_COMPLETE','strategy':'szse_monthly_low_pe','phase':'dev',
        'start':'2024-01-02','source_warmup_start':START,'end':END,
        'results_by_profile':results,'method_code_sha256':plan['method_code_sha256'],'plan_sha256':args.expected_plan_sha256,
        'raw_development_confirmation_passes':confirmation_passes(results),'reference_CNY':'1000000',
        'confirmation_rule':'All three registered participation levels at40bp: both development years positive, exposure>=90%, verified zero entitlements.',
        'tape_accessed_sessions':len(bank.accessed),'derived_events_sha256':sha256_file(out/'derived_events.json'),
        'zero_entitlement_proofs_sha256':sha256_file(out/'zero_entitlement_proofs.json'),
        'source_evidence_level':'RECONSTRUCTED_ENGINEERING_SIMULATION','queue_and_impact_calibrated':False,
        '2026_strategy_returns_queried':False,'sealed_evidence':False,'objective_achieved':False}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print('exchange value development complete',result['raw_development_confirmation_passes'],flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
