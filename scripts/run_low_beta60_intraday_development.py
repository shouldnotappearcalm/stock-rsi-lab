"""Six frozen pre2026 physical nested-execution diagnostics; no alpha changes."""
import argparse,json,math
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from functools import partial
from pathlib import Path
from scripts.run_low_beta60_raw_development import METHOD_FILES as RAW_METHODS,validate_compiled_reference_coverage
from scripts.admit_low_beta60_minutes_pre2026 import METHOD_FILES as ADMISSION_METHODS
from scripts.capture_low_beta60_minutes_pre2026 import authenticate,valid_pair
from scripts.capture_low_beta60_minutes_pre2026_v2 import METHOD_FILES as GUARD_METHODS,capture_prefix_v2
from scripts.prepare_low_beta60_account_sources import verify_packet
from scripts.fundamental_query_journal import file_sha
from scripts.run_low_risk_intraday_replay import TapeBank,write_case
from scripts.run_low_risk_raw_share_validation import clean,summarize_case
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

PARTICIPATION=(100,500,1000);EXTRA_BPS=(20,40);CAPITAL='1000000';END='2025-12-31'
METHOD_FILES=tuple(dict.fromkeys((*RAW_METHODS,*ADMISSION_METHODS,*GUARD_METHODS,
 'scripts/run_low_beta60_intraday_development.py','scripts/run_low_risk_intraday_replay.py',
 'src/stock_rsi/intraday_broker.py','src/stock_rsi/intraday_tape.py')))


class CompletePrefixTapeBank(TapeBank):
    def __init__(self,capture,bars,end=END):
        capture=Path(capture);m=json.loads((capture/'manifest.json').read_text())
        if m['complete_capture'] is not True or file_sha(capture/'plan.json')!=m['plan_sha256']:
            raise ValueError('complete authenticated prefix capture required')
        self.index={};self.cache={};self.accessed=set();self.bars=bars;self.end=end
        for name,h in m['per_session_sha256'].items():
            if Path(name).name!=name or not name.endswith('.json'):raise ValueError('safe prefix filename required')
            code,day=name[:-5].split('-',1);valid_pair(code,day)
            if day>end or code not in bars or day not in bars[code]:raise ValueError('tape outside frozen raw prefix')
            self.index[(code,day)]=(capture/'sessions'/name,h)
    def __call__(self,code,day):
        key=(code,day.isoformat())
        if day.isoformat()>self.end or key not in self.index:raise ValueError('future or missing frozen prefix tape')
        path,h=self.index[key]
        if file_sha(path)!=h:raise ValueError('source tape bytes changed, including cached tape')
        return super().__call__(code,day)


def confirmation_passes(results):
    if set(results)!={f'{p}/{cost}' for p in PARTICIPATION for cost in EXTRA_BPS}:return False
    for p in PARTICIPATION:
        r=results[f'{p}/40'];values=[r.get(k) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct')]
        if (r.get('status')!='NESTED_EXECUTION_ACCOUNT_RECONCILED' or r.get('monthly_decisions')!=24
                or r.get('account_sessions')!=485 or r.get('whole_day_volume_violations')!=0
                or r.get('noncash_entitlements_supported') is not True
                or not all(type(v) in (float,int) and math.isfinite(v) for v in values)
                or min(values[:2])<=0 or values[2]<90):return False
    return True


def load_inputs(base,repo,plan):
    for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
        for name,h in plan[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(parent/name)!=h:
                raise ValueError('frozen intraday code/evidence/source bytes changed')
    rq=repo/'experiments/qlib/low-beta60-minute-gap-identities.json';cp=repo/'experiments/qlib/low-beta60-minute-capture-plan.json'
    request=json.loads(rq.read_text());capture_plan=json.loads(cp.read_text());reused,fresh=authenticate(base,repo,request,capture_plan)
    capture=base/'low-beta60-minutes-dev-20261021'
    def no_source(*args):raise AssertionError('source calls forbidden during account replay')
    capture_prefix_v2(base,capture,reused,fresh,capture_plan,no_source,
        expected_manifest_sha256=plan['local_source_sha256']['low-beta60-minutes-dev-20261021/manifest.json'])
    admission_dir=base/'low-beta60-minute-admission-20261021';admission=json.loads((admission_dir/'summary.json').read_text())
    minute_audit=json.loads((base/'low-beta60-minute-independent-audit-20261021.json').read_text())
    if (admission['admitted_for_reconstructed_execution'] is not True
            or admission['status_counts']!={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':1332}
            or file_sha(admission_dir/'details.json')!=admission['details_sha256']
            or admission['capture_manifest_sha256']!=file_sha(capture/'manifest.json')
            or minute_audit['admission_summary_sha256']!=file_sha(admission_dir/'summary.json')
            or minute_audit['reconstructed_source_admission_passes'] is not True
            or minute_audit['source_pairs_reconstructed']!=1332 or minute_audit['imports_project_code'] is not False
            or not all(minute_audit['semantic_negative_controls_rejected'].values())
            or minute_audit['audit_code_sha256']!=file_sha(repo/'experiments/qlib/audit_sources/2026-10-21-low-beta60-minute-source-audit.py')):
        raise ValueError('complete independently verified minute source admission absent')
    daily_dir=base/'low-beta60-raw-daily-development-20261021';daily=json.loads((daily_dir/'summary.json').read_text())
    daily_audit=json.loads((base/'low-beta60-raw-daily-independent-audit-20261021.json').read_text())
    if (daily['raw_daily_proxy_development_gate_passes'] is not True
            or daily_audit['raw_daily_proxy_development_gate_passes_independently'] is not True
            or daily_audit['summary_sha256']!=file_sha(daily_dir/'summary.json')):raise ValueError('original physical daily confirmation absent')
    for cost,r in daily['results_by_extra_bps'].items():
        for name,h in r['artifact_sha256'].items():
            if Path(name).name!=name or file_sha(daily_dir/cost/name)!=h:raise ValueError('prior daily account artifact changed')
    raw=base/'low-beta60-raw-dev-20261021';m=json.loads((raw/'manifest.json').read_text())
    sessions=json.loads((raw/'calendar.json').read_text())['sessions']
    if file_sha(raw/'calendar.json')!=m['calendar_sha256'] or len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=['2023-12-29',END]:
        raise ValueError('complete original pre2026 calendar required')
    calendar=TradingCalendar(sessions);packets={}
    for c,h in m['per_code_sha256'].items():
        f=raw/'codes'/(c+'.json')
        if file_sha(f)!=h:raise ValueError('raw packet changed')
        packet=json.loads(f.read_text());verify_packet(c,packet,sessions);packets[c]=packet
    tf=base/'low-beta60-pre2026-formations-20261021/targets.json'
    if file_sha(tf)!=m['target_sha256']:raise ValueError('same original monthly targets required')
    targets=json.loads(tf.read_text())['low_beta60']
    if len(targets)!=24 or len(packets)!=69 or {c for t in targets.values() for c in t['weights']}!=set(packets):
        raise ValueError('complete original69names/24targets required')
    source=base/'low-beta60-account-source-events-20261021';ss=json.loads((source/'summary.json').read_text())
    source_audit=json.loads((base/'low-beta60-event-source-independent-audit-20261021.json').read_text())
    if (source_audit['summary_sha256']!=file_sha(source/'summary.json') or source_audit['events_reconstructed']!=179
            or ss['raw_manifest_sha256']!=file_sha(raw/'manifest.json') or ss['target_sha256']!=file_sha(tf)):
        raise ValueError('independently reconstructed original event source binding absent')
    for name,h in ss['artifact_sha256'].items():
        if Path(name).name!=name or file_sha(source/name)!=h:raise ValueError('compiled source artifact changed')
    proofs=json.loads((source/'effective_proofs.json').read_text());proofdir=base/'low-beta60-corporate-reviewed-20261021'
    if proofs['source_reviewed_manifest_sha256']!=file_sha(proofdir/'reviewed-manifest.json'):raise ValueError('primary evidence projection changed')
    for d in proofs['documents']:
        if Path(d['file']).name!=d['file'] or d['day']>END or file_sha(proofdir/d['file'])!=d['sha256']:raise ValueError('original primary PDF changed')
    events,receipts=compile_distribution_events_v2(packets,proofs,calendar)
    if len(events)!=179 or clean([asdict(e) for e in events])!=json.loads((source/'derived_events.json').read_text()) or list(receipts)!=json.loads((source/'event_source_receipts.json').read_text()):
        raise ValueError('original179economic events/receipts differ from independent reconstruction')
    validate_compiled_reference_coverage(packets,events)
    bars={c:{r['date']:r for r in v['bars']} for c,v in packets.items()};bank=CompletePrefixTapeBank(capture,bars)
    if set(bank.index)!={(c,d) for c,d in request['active_requests']}:raise ValueError('full potential execution prefix required')
    return calendar,bars,events,receipts,targets,bank


def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('source-root','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+name,required=True)
    a=p.parse_args(argv);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
    if out.exists():raise ValueError('preserve prior intraday development attempt')
    if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('frozen account plan changed')
    plan=json.loads(Path(a.plan).read_text())
    if (plan['status']!='FROZEN_BEFORE_LOW_BETA60_INTRADAY_DEVELOPMENT_OUTCOMES'
            or plan['participation_bps']!=list(PARTICIPATION) or plan['extra_cost_bps']!=list(EXTRA_BPS)
            or plan['initial_CNY']!=CAPITAL or plan['window']!=['2023-12-29',END]
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)):
        raise ValueError('fixed six-profile development method changed')
    calendar,bars,events,receipts,targets,bank=load_inputs(base,repo,plan)
    out.mkdir(parents=True);results={};event_by_id={e.event_id:e for e in events}
    (out/'derived_events.json').write_text(json.dumps(clean([asdict(e) for e in events]),indent=2)+'\n')
    (out/'event_source_receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
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
            except (ValueError,KeyError,ArithmeticError) as exc:
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
    summary={'status':'LOW_BETA60_INTRADAY_DEVELOPMENT_COMPLETE','policy_id':'low_beta60','phase':'dev',
        'window':['2023-12-29',END],'initial_CNY':CAPITAL,'results_by_profile':results,
        'method_code_sha256':plan['method_code_sha256'],'plan_sha256':a.expected_plan_sha256,
        'raw_development_confirmation_passes':confirmation_passes(results),'reference_extra_bps':40,
        'confirmation_rule':'All3participations at40extra bps:valid485days/24intents,both yearspositive,averageexposure>=90,noncash evidence supported',
        'tape_accessed_pairs':len(bank.accessed),'source_prefix_pairs':len(bank.index),
        'derived_events_sha256':file_sha(out/'derived_events.json'),'event_source_receipts_sha256':file_sha(out/'event_source_receipts.json'),
        'base_costs':'buy5/sell15bps,min5CNY perchild plus separatelyrounded extra20/40bps',
        'tax_model':'flat20percent cash+taxablebonus stress,not actualFIFO;cashnextsessionafterpay',
        'source_evidence_level':'RECONSTRUCTED_ENGINEERING_SIMULATION','all_profiles_independently_audited':False,
        'queue_and_impact_calibrated':False,'historical_arrival_verified':False,'actual_FIFO_tax_liability_verified':False,
        'full_corporate_actions_certified':False,'2026_strategy_returns_queried':False,'sealed_evidence':False,
        'candidate_promoted':False,'objective_achieved':False}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('intraday development complete;all-reference gate',summary['raw_development_confirmation_passes'],flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
