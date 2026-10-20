"""Two frozen pre2026 engineering diagnostics using the existing physical engine."""
import argparse,json,math
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path

from scripts.prepare_low_beta60_account_sources import file_sha,verify_packet
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from scripts.run_low_risk_raw_share_validation import clean,summarize_case,validate_source_coverage
from scripts.run_low_risk_feedback_cost_stress import write_case
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

METHOD_FILES=('scripts/run_low_beta60_raw_development.py','scripts/prepare_low_beta60_account_sources.py',
 'scripts/replay_stock_distribution_targets.py','scripts/run_low_risk_raw_share_validation.py',
 'scripts/run_low_risk_feedback_cost_stress.py','src/stock_rsi/distribution_event_compiler_v2.py',
 'src/stock_rsi/distribution_event_compiler.py','src/stock_rsi/stock_distribution_account.py',
 'src/stock_rsi/raw_share_account.py','src/stock_rsi/execution_cost.py','src/stock_rsi/broker.py',
 'src/stock_rsi/calendar.py','src/stock_rsi/data.py','src/stock_rsi/models.py','src/stock_rsi/time.py',
 'src/stock_rsi/lifecycle_source_rows.py','scripts/capture_low_risk_raw_account_data.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/prepare_qlib_master_market_pre2026.py')


def validate_compiled_reference_coverage(packets,events):
    """Coverage uses authenticated event dates, never edits vendor packets."""
    projected=deepcopy(packets)
    for packet in projected.values():packet['distributions']=[]
    for event in events:
        projected[event.instrument]['distributions'].append({'dividOperateDate':event.ex_date.isoformat()})
    validate_source_coverage(projected)


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
    if out.exists():raise ValueError('preserve previous raw development diagnostic')
    if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('raw diagnostic plan changed')
    plan=json.loads(Path(a.plan).read_text())
    if (plan['status']!='FROZEN_LOW_BETA60_RAW_DAILY_ENGINEERING_DIAGNOSTIC'
            or plan['initial_CNY']!='1000000' or plan['extra_cost_bps']!=[20,40]
            or plan['window']!=['2023-12-29','2025-12-31']
            or plan['policy_id']!='low_beta60' or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or any(file_sha(repo/n)!=h for n,h in plan['method_code_sha256'].items())):
        raise ValueError('raw engineering method/profiles changed')
    for field,root in (('local_source_sha256',base),('public_evidence_sha256',repo)):
        for name,h in plan[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(root/name)!=h:
                raise ValueError('frozen raw input/evidence changed')
    if (plan['protocol_file']!='docs/research/low-beta60-raw-daily-plan-2026-10-21.md'
            or file_sha(repo/plan['protocol_file'])!=plan['protocol_sha256']):raise ValueError('raw diagnostic protocol changed')
    raw=base/'low-beta60-raw-dev-20261021';source=base/'low-beta60-account-source-events-20261021'
    m=json.loads((raw/'manifest.json').read_text());ss=json.loads((source/'summary.json').read_text())
    audit=json.loads((base/'low-beta60-event-source-independent-audit-20261021.json').read_text())
    if (audit['status']!='INDEPENDENT_179_EVENT_ECONOMICS_IDENTITIES_AND_SOURCE_RECEIPTS_RECONSTRUCTED'
            or audit['summary_sha256']!=file_sha(source/'summary.json') or audit['events_reconstructed']!=179
            or not all(audit['negative_controls_rejected'].values())
            or ss['raw_manifest_sha256']!=file_sha(raw/'manifest.json')
            or ss['source_packet_sha256']!=m['per_code_sha256']):raise ValueError('source compilation audit not bound')
    for name,h in ss['artifact_sha256'].items():
        if Path(name).name!=name or file_sha(source/name)!=h:raise ValueError('compiled artifact changed')
    if file_sha(raw/'calendar.json')!=m['calendar_sha256']:raise ValueError('raw exchange calendar changed')
    sessions=json.loads((raw/'calendar.json').read_text())['sessions']
    if len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=plan['window']:
        raise ValueError('complete pre2026 source sessions required')
    calendar=TradingCalendar(sessions);packets={}
    for code,h in m['per_code_sha256'].items():
        path=raw/'codes'/(code+'.json')
        if file_sha(path)!=h:raise ValueError('raw packet changed')
        packet=json.loads(path.read_text());verify_packet(code,packet,sessions);packets[code]=packet
    targetfile=base/'low-beta60-pre2026-formations-20261021/targets.json'
    if file_sha(targetfile)!=m['target_sha256'] or ss['target_sha256']!=m['target_sha256']:
        raise ValueError('original frozen monthly target changed')
    targets=json.loads(targetfile.read_text())['low_beta60']
    if len(targets)!=24 or len(packets)!=69 or {c for t in targets.values() for c in t['weights']}!=set(packets):
        raise ValueError('complete original24targets/69source universe required')
    effective=json.loads((source/'effective_proofs.json').read_text())
    proofdir=base/'low-beta60-corporate-reviewed-20261021'
    if effective['source_reviewed_manifest_sha256']!=file_sha(proofdir/'reviewed-manifest.json'):
        raise ValueError('reviewed source projection changed')
    for d in effective['documents']:
        if Path(d['file']).name!=d['file'] or d['day']>'2025-12-31' or file_sha(proofdir/d['file'])!=d['sha256']:
            raise ValueError('reviewed original PDF changed')
    events,receipts=compile_distribution_events_v2(packets,effective,calendar)
    if (clean([asdict(e) for e in events])!=json.loads((source/'derived_events.json').read_text())
            or list(receipts)!=json.loads((source/'event_source_receipts.json').read_text())):
        raise ValueError('source event compilation differs from frozen artifacts')
    validate_compiled_reference_coverage(packets,events)
    bars={c:{r['date']:r for r in v['bars']} for c,v in packets.items()}
    out.mkdir(parents=True);results={}
    for bps in plan['extra_cost_bps']:
        folder=out/str(bps);folder.mkdir();holders=[]
        def factory(cal,cash,distributions,**kw):
            acct=StockDistributionAccount(cal,cash,distributions,
                broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps),**kw)
            holders.append(acct);return acct
        print('low-beta60 raw daily development',bps,'bp',flush=True)
        try:
            case=simulate_fixed_targets(calendar,bars,events,targets,plan['initial_CNY'],lifecycles={},
                account_factory=factory,policy_id='low_beta60')
            if len(case['intents'])!=24:raise ValueError('complete24monthly decisions required')
            artifacts=write_case(folder,case);days=[r for r in case['days'] if r['day']>='2024-01-02']
            if len(days)!=485 or any(r['day']>'2025-12-31' for r in case['days']):raise ValueError('development account date scope changed')
            exposure=float(sum((r['exposure'] for r in days),Decimal(0))/len(days)*100)
            peak=Decimal(plan['initial_CNY']);dd=Decimal(0)
            for row in days:peak=max(peak,row['equity']);dd=min(dd,row['equity']/peak-1)
            result={'status':'RAW_DAILY_PROXY_RECONCILED' if case['whole_day_volume_violations']==0 else 'INVALID_WHOLE_DAY_VOLUME',
                **summarize_case(case,plan['initial_CNY']),'average_exposure_pct':exposure,
                'max_drawdown_pct':float(dd*100),'account_sessions':len(days),'artifact_sha256':artifacts}
        except (ValueError,KeyError,ArithmeticError) as exc:
            result={'status':'INVALID_ACCOUNT_OR_SOURCE','error_type':type(exc).__name__,'error':str(exc)}
            if holders:
                acct=holders[0];state=clean({'last_account_clock':acct._last_clock,'cash':acct.broker.cash,
                    'positions':acct.broker.positions,'orders':acct.broker.orders,'fills':acct.broker.fills,
                    'owned_shares':acct.owned_quantities(),'corporate_ledger':acct.corporate_ledger,
                    'cash_claims':acct.cash_claims,'stock_claims':acct.stock_claims})
                (folder/'failed_account_state.json').write_text(json.dumps(state,indent=2)+'\n')
            (folder/'error.json').write_text(json.dumps(result,indent=2)+'\n')
            result['failure_artifact_sha256']={f.name:file_sha(f) for f in folder.iterdir()}
        results[str(bps)]=result;(out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
    ref=results['40'];values=[ref.get(k,float('nan')) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct')]
    passes=(ref['status']=='RAW_DAILY_PROXY_RECONCILED' and all(math.isfinite(v) for v in values)
        and min(values[:2])>0 and values[2]>=90)
    summary={'status':'LOW_BETA60_RAW_DAILY_DEVELOPMENT_ENGINEERING_DIAGNOSTIC_COMPLETE',
        'plan_sha256':a.expected_plan_sha256,'method_code_sha256':plan['method_code_sha256'],
        'results_by_extra_bps':results,'reference_CNY':'1000000','reference_extra_bps':40,
        'raw_daily_proxy_development_gate_passes':passes,'raw_account_independently_audited':False,
        'tax_model':'20percent cash+taxablebonus stress reserve, not actual FIFO tax settlement',
        'base_costs':'buy5/sell15 bps, minimum5CNY per fill; extra20/40bps separately rounded and added',
        'annual_return_denominators':'2024:initial1m;2025:2024-12-31 continuous account equity; no reset',
        'execution_model':'prior-close integer quantities; next-session daily-open;9.5percent limit proxy',
        'cash_available_rule':'next explicit source session after published payment date',
        'minute_execution_admitted':False,'historical_arrival_certified':False,'full_corporate_actions_certified':False,
        'queue_and_impact_calibrated':False,'actual_FIFO_tax_liability_verified':False,
        '2026_return_computed':False,'new_2026_queries':False,'candidate_promoted':False,'objective_achieved':False}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('raw daily diagnostic complete; development gate',passes,flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
