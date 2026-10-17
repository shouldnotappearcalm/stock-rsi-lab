"""Frozen diagnostic: reproduce all development accounts before evaluating 2026."""
import argparse
import json
from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
from scripts.capture_szse_value_raw_extension import START,END,full_target_codes
from scripts.prepare_szse_value_frozen_2026_targets import assert_cap_only_change
from scripts.reversal_full_inputs import prepare_events,resolve_cash_components
from scripts.run_low_risk_intraday_replay import (
    PARTICIPATION,EXTRA_BPS,TapeBank,write_case,authenticate_development,compare_development_prefix,
)
from scripts.run_low_risk_raw_share_validation import CAPITALS,clean,simulate_fixed_targets,summarize_case,validate_source_coverage
from scripts.run_szse_value_intraday_development import METHOD_FILES as DEVELOPMENT_FILES
from stock_rsi.calendar import TradingCalendar
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.raw_share_account import RawShareAccount

METHOD_FILES=tuple(dict.fromkeys((*DEVELOPMENT_FILES,'scripts/run_szse_value_frozen_2026.py',
    'scripts/reversal_full_inputs.py','scripts/capture_reversal_raw_extension.py',
    'scripts/capture_szse_value_raw_extension.py','src/stock_rsi/exchange_value_extended.py',
    'scripts/prepare_szse_value_frozen_2026_targets.py')))


def combined_2025_2026(case):
    base=next(r['equity'] for r in case['days'] if r['day']=='2024-12-31')
    rows=[r for r in case['days'] if '2025-01-01'<=r['day']<=END];peak=base;drawdown=Decimal(0)
    for row in rows:
        peak=max(peak,row['equity']);drawdown=min(drawdown,row['equity']/peak-1)
    return {'net_compound_return_pct':float((rows[-1]['equity']/base-1)*100),
        'max_drawdown_pct':float(drawdown*100),'average_exposure_pct':float(sum((r['exposure'] for r in rows),Decimal(0))/len(rows)*100),
        'sessions':len(rows),'ending_equity':str(rows[-1]['equity'])}


def assert_development_control(folder,old,old_event_ids):
    compare_development_prefix(folder,old)
    def read(root,name):return json.loads((root/(name+'.json')).read_text())
    for name,clock in (('intents','execution_session'),('parent_instructions','eligible_at')):
        if [r for r in read(folder,name) if r[clock]<'2026-01-01']!=read(old,name):
            raise RuntimeError('development '+name+' changed')
    if {day:q for day,q in read(folder,'ownership').items() if day<'2026-01-01'}!=read(old,'ownership'):
        raise RuntimeError('development ownership changed')
    corporate=[r for r in read(folder,'corporate_ledger') if r['day']<'2026-01-01']
    if [r for r in corporate if r['event_id'] in old_event_ids]!=read(old,'corporate_ledger'):
        raise RuntimeError('development original corporate ledger changed')
    for row in corporate:
        if row['event_id'] in old_event_ids:continue
        if row['kind']=='RECORD_DATE_OWNERSHIP':valid=row['quantity']==0
        elif row['kind']=='EX_DATE_ENTITLEMENT':
            valid=(row['registered_quantity']==0 and row['capital_shares']==0
                   and Decimal(row['cash_gross'])==0 and Decimal(row['stress_tax_reserve'])==0)
        else:valid=False
        if not valid:raise RuntimeError('new historical source event changed pre2026 entitlement')


def replay_profile(calendar,bars,events,targets,zero,bank,participation,cost,capital):
    holders=[]
    def factory(cal,cash,distributions,**kwargs):
        constructor=partial(IntradayBroker,participation_bps=participation,extra_cost_bps=cost,tape_provider=bank)
        account=RawShareAccount(cal,cash,distributions,broker_factory=constructor,**kwargs);holders.append(account.broker);return account
    case=simulate_fixed_targets(calendar,bars,events,targets,capital,account_factory=factory)
    if len(case['intents'])!=(24 if calendar.days[-1].year==2025 else 34):raise ValueError('monthly decision coverage changed')
    by_id={e.event_id:e for e in events};start,end=calendar.days[0],calendar.days[-1]
    rec_ids={p['event_id'] for p in zero if start<=by_id[p['event_id']].recorded<=end}
    ex_ids={p['event_id'] for p in zero if start<=by_id[p['event_id']].ex_date<=end}
    rec={r['event_id']:r['quantity'] for r in case['corporate_ledger'] if r['kind']=='RECORD_DATE_OWNERSHIP' and r['event_id'] in rec_ids}
    ex={r['event_id']:r['registered_quantity'] for r in case['corporate_ledger'] if r['kind']=='EX_DATE_ENTITLEMENT' and r['event_id'] in ex_ids}
    if set(rec)!=rec_ids or set(ex)!=ex_ids or any(rec.values()) or any(ex.values()):raise ValueError('zero-entitlement proof violated')
    case['parent_instructions']=case.pop('orders');case['orders']=holders[0].child_orders
    return case


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('raw-data-dir','proof-dir','targets','target-receipt','old-tape-dir','extra-tape-dir',
                 'development-dir','development-audit','plan','expected-plan-sha256','output-dir'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
    if out.exists():raise ValueError('frozen diagnostic output already exists')
    if sha256_file(args.plan)!=args.expected_plan_sha256:raise ValueError('frozen diagnostic plan changed')
    plan=json.loads(Path(args.plan).read_text())
    if (plan['status']!='FROZEN_BEFORE_SZSE_VALUE_2026_OUTCOMES' or plan['participation_bps']!=list(PARTICIPATION)
            or plan['extra_bps']!=list(EXTRA_BPS) or plan['capitals']!=list(CAPITALS)
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(root/n)!=h for n,h in plan['method_code_sha256'].items())):raise ValueError('diagnostic method changed')
    dev=Path(args.development_dir);oldplan=root/'experiments/qlib/szse-value-intraday-development-plan.json'
    if sha256_file(oldplan)!=plan['development_plan_sha256']:raise ValueError('tested development plan changed')
    dp=json.loads(oldplan.read_text())
    if any(sha256_file(root/n)!=h for n,h in dp['method_code_sha256'].items()):
        raise ValueError('tested account/execution dependency changed')
    assert_cap_only_change((root/'src/stock_rsi/exchange_value.py').read_text(),(root/'src/stock_rsi/exchange_value_extended.py').read_text())
    authenticate_development(dev,{'development_summary_sha256':plan['development_summary_sha256'],'method_code_sha256':dp['method_code_sha256']})
    prior=json.loads((dev/'summary.json').read_text())
    if prior['plan_sha256']!=plan['development_plan_sha256'] or prior['raw_development_confirmation_passes'] is not True:
        raise ValueError('required development confirmation absent')
    if sha256_file(args.development_audit)!=plan['development_audit_sha256']:raise ValueError('independent development audit changed')
    audit=json.loads(Path(args.development_audit).read_text())
    if audit['replay_summary_sha256']!=plan['development_summary_sha256'] or audit['valid_profiles']!=60 or audit['raw_confirmation_passes_independently'] is not True:
        raise ValueError('development independent confirmation absent')
    for file,key in (('derived_events.json','derived_events_sha256'),('zero_entitlement_proofs.json','zero_entitlement_proofs_sha256')):
        if sha256_file(dev/file)!=prior[key]:raise ValueError('development source-event artifact changed')
    old_event_ids={e['event_id'] for e in json.loads((dev/'derived_events.json').read_text())}
    if sha256_file(args.targets)!=plan['target_sha256'] or sha256_file(args.target_receipt)!=plan['target_receipt_sha256']:
        raise ValueError('frozen target identity changed')
    receipt=json.loads(Path(args.target_receipt).read_text())
    if receipt['targets_sha256']!=plan['target_sha256'] or receipt['development_prefix_reproduced'] is not True:
        raise ValueError('target formation prefix not authenticated')
    raw,proofdir,old,extra=map(Path,(args.raw_data_dir,args.proof_dir,args.old_tape_dir,args.extra_tape_dir))
    for path,key in ((raw/'manifest.json','raw_manifest_sha256'),(proofdir/'reviewed-manifest.json','proof_manifest_sha256'),
                     (old/'manifest.json','old_tape_manifest_sha256'),(extra/'manifest.json','extra_tape_manifest_sha256')):
        if sha256_file(path)!=plan[key]:raise ValueError('diagnostic source identity changed')
    m=json.loads((raw/'manifest.json').read_text());proof=json.loads((proofdir/'reviewed-manifest.json').read_text())
    if (proof['raw_manifest_sha256']!=plan['raw_manifest_sha256'] or proof['target_sha256']!=plan['target_sha256']
            or sha256_file(proofdir/'manifest.json')!=proof['capture_manifest_sha256']
            or sha256_file(raw/'calendar.json')!=m['calendar_sha256']):raise ValueError('source provenance changed')
    original_proof=root/'experiments/qlib/szse-value-corporate-reviewed-manifest.json'
    if sha256_file(original_proof)!=proof['development_reviewed_manifest_sha256']:raise ValueError('development primary proof changed')
    op=json.loads(original_proof.read_text())
    if proof['supplementary_distributions'][:len(op['supplementary_distributions'])]!=op['supplementary_distributions']:
        raise ValueError('original primary supplements changed')
    docs={d['file']:d for d in proof['documents']}
    if len(docs)!=len(proof['documents']):raise ValueError('duplicate primary source document')
    for name,d in docs.items():
        if Path(name).name!=name or d['day']>END or sha256_file(proofdir/name)!=d['sha256']:raise ValueError('primary notice changed')
    references=[*proof['supplementary_distributions'],*proof.get('resolved_cash_components',[])]
    for item in references:
        d=docs[item['source_file']];row=item.get('record',item.get('replacement_record'))
        if d['sha256']!=item['source_sha256'] or d['instrument']!=item['instrument'] or d['day']!=row['dividPlanDate']:
            raise ValueError('primary source reference does not bind event')
    sessions=json.loads((raw/'calendar.json').read_text())['sessions']
    if sessions[0]!=START or sessions[-1]!=END or sessions!=sorted(set(sessions)):raise ValueError('complete frozen account calendar required')
    targets=json.loads(Path(args.targets).read_text());codes=full_target_codes(targets)
    if set(codes)!=set(m['per_code_sha256']):raise ValueError('complete fixed source universe required')
    packets={}
    for code in codes:
        path=raw/'codes'/(code+'.json')
        if sha256_file(path)!=m['per_code_sha256'][code]:raise ValueError('raw source packet changed')
        p=json.loads(path.read_text())
        if p['instrument']!=code or p['window']!=[START,END] or [r['date'] for r in p['bars']]!=sessions:raise ValueError('raw coverage changed')
        packets[code]=p
    for key,tax in proof['capital_tax'].items():
        if tax.get('verified_exempt') is not True:continue
        code,day=key.split('|');d=docs[tax['source_file']];rows=[r for r in packets[code]['distributions'] if r['dividOperateDate']==day]
        if (len(rows)!=1 or d['sha256']!=tax['source_sha256'] or d['instrument']!=code
                or d['day']!=rows[0]['dividPlanDate'] or Decimal(rows[0]['dividReserveToStockPs'])!=Decimal(tax['expected_capital_per_share'])):
            raise ValueError('capital-transfer exemption not bound to original source event')
    resolved,resolution=resolve_cash_components(packets,proof)
    merged,events,zero=prepare_events(resolved,targets,proof);validate_source_coverage(merged)
    bars={c:{r['date']:r for r in p['bars']} for c,p in merged.items()};out.mkdir(parents=True)
    for file,value in (('derived_events.json',clean([asdict(e) for e in events])),('zero_entitlement_proofs.json',zero),('resolution_receipts.json',resolution)):
        (out/file).write_text(json.dumps(value,indent=2)+'\n')
    controls={};development_calendar=TradingCalendar([d for d in sessions if d<'2026-01-01'])
    development_targets={d:t for d,t in targets.items() if d<'2026-01-01'};development_bank=TapeBank(old,extra,bars,'2025-12-31')
    for participation in PARTICIPATION:
        for cost in EXTRA_BPS:
            for capital in CAPITALS:
                label=f'{participation}/{cost}/{capital}';folder=out/'development_control'/label;folder.mkdir(parents=True)
                print('value development control '+label,flush=True)
                case=replay_profile(development_calendar,bars,events,development_targets,zero,development_bank,participation,cost,capital)
                artifacts=write_case(folder,case);assert_development_control(folder,dev/label,old_event_ids)
                controls[label]={'status':'DEVELOPMENT_CONTROL_MATCHED','artifact_sha256':artifacts}
    if len(controls)!=60 or any(day>'2025-12-31' for code,day in development_bank.accessed):raise RuntimeError('development control date/coverage failed')
    (out/'development_controls.json').write_text(json.dumps(controls,indent=2)+'\n')
    print('all60 development financial controls reproduced; opening frozen2026 replay',flush=True)
    calendar=TradingCalendar(sessions);bank=TapeBank(old,extra,bars,END);results={}
    for participation in PARTICIPATION:
        for cost in EXTRA_BPS:
            for capital in CAPITALS:
                label=f'{participation}/{cost}/{capital}';folder=out/label;folder.mkdir(parents=True)
                print('value full diagnostic '+label,flush=True)
                try:
                    case=replay_profile(calendar,bars,events,targets,zero,bank,participation,cost,capital)
                    artifacts=write_case(folder,case);assert_development_control(folder,dev/label,old_event_ids)
                    results[label]={'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED',**summarize_case(case,capital),
                        '2025_through_'+END:combined_2025_2026(case),
                        'development_prefix_reproduced':True,'zero_entitlements_verified':True,
                        'unfilled_parents':sum(p['remaining']>0 for p in case['parent_instructions']),'artifact_sha256':artifacts}
                except (ValueError,KeyError) as exc:
                    results[label]={'status':'INVALID_SOURCE_OR_ACCOUNT','error':str(exc)}
                    (folder/'error.json').write_text(json.dumps(results[label],indent=2)+'\n')
                (out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
    numeric=[label for label,r in results.items() if r['status']=='NESTED_EXECUTION_ACCOUNT_RECONCILED'
        and min(r['2024_return_pct'],r['2025_return_pct'])>0 and r['2026_through_'+END]['net_compound_return_pct']>=10]
    summary={'status':'FROZEN_SZSE_VALUE_2026_DIAGNOSTIC_COMPLETE','strategy':'szse_monthly_low_pe','phase':'full','end':END,
        'results_by_profile':results,'numeric_threshold_profiles_at_interim_cutoff':numeric,'development_controls_reproduced':60,
        'development_control_tape_sessions':len(development_bank.accessed),'full_tape_sessions':len(bank.accessed),
        'method_code_sha256':plan['method_code_sha256'],'plan_sha256':args.expected_plan_sha256,
        'derived_events_sha256':sha256_file(out/'derived_events.json'),'zero_entitlement_proofs_sha256':sha256_file(out/'zero_entitlement_proofs.json'),
        'resolution_receipts_sha256':sha256_file(out/'resolution_receipts.json'),'development_controls_sha256':sha256_file(out/'development_controls.json'),
        'complete_requested_October':False,'queue_and_impact_calibrated':False,'historical_arrival_verified':False,
        '2026_returns_used_to_change_investment_rule':False,'sealed_evidence':False,'objective_achieved':False}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('frozen value diagnostic complete',len(numeric),'numeric profiles',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
