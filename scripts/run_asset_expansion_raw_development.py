"""Frozen primary integer-share daily proxy; no signal search or2026 values."""
import argparse
from dataclasses import asdict
from decimal import Decimal
from functools import partial
import json
import math
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from scripts.run_low_risk_raw_share_validation import clean,summarize_case,validate_source_coverage
from scripts.run_low_risk_feedback_cost_stress import write_case
from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.stock_distribution_account import StockDistributionAccount

CANDIDATE='low_asset_expansion_decile_conditional'
RAW='asset-expansion-raw-pre2026-20261022'
TARGET='asset-expansion-conditional-development-v1-20261022/targets.json'
PROTOCOL='docs/research/asset-expansion-primary-and-raw-plan-2026-10-22.md'
METHOD_FILES=('scripts/run_asset_expansion_raw_development.py','scripts/replay_stock_distribution_targets.py',
    'scripts/run_low_risk_raw_share_validation.py','scripts/run_low_risk_feedback_cost_stress.py',
    'scripts/capture_low_risk_raw_account_data.py','scripts/prepare_qlib_master_market_pre2026.py',
    'scripts/fundamental_query_journal.py','src/stock_rsi/distribution_event_compiler.py',
    'src/stock_rsi/stock_distribution_account.py','src/stock_rsi/raw_share_account.py',
    'src/stock_rsi/broker.py','src/stock_rsi/execution_cost.py','src/stock_rsi/calendar.py',
    'src/stock_rsi/data.py','src/stock_rsi/models.py','src/stock_rsi/time.py',
    'src/stock_rsi/lifecycle_source_rows.py','tests/test_asset_expansion_raw_development.py')


def read(p):return json.loads(Path(p).read_text())


def restoration_receipts(packet):
    """Classify only an exact next-session cumulative-factor restoration."""
    rows=packet['bars'];indices={r['date']:i for i,r in enumerate(rows)}
    ex={r['dividOperateDate'] for r in packet['distributions']};adjustments={r['dividOperateDate']:r for r in packet['adjustments']}
    if len(adjustments)!=len(packet['adjustments']):raise ValueError('duplicate adjustment dates need source review')
    receipts=[]
    for at,current in adjustments.items():
        if at in ex:continue
        i=indices.get(at,0);previous_day=rows[i-1]['date'] if i else None;previous=adjustments.get(previous_day)
        if (previous_day not in ex or previous is None or Decimal(previous['adjustFactor'])!=1
                or any(Decimal(previous[f])!=Decimal(current[f]) for f in ('foreAdjustFactor','backAdjustFactor'))
                or Decimal(current['adjustFactor'])!=Decimal(current['backAdjustFactor'])
                or Decimal(current['backAdjustFactor'])<=0
                or Decimal(rows[i]['preclose'])!=Decimal(rows[i-1]['close'])):
            raise ValueError('unexplained adjustment is not exact next-session restoration')
        receipts.append({'instrument':packet['instrument'],'distribution_day':previous_day,'restoration_day':at,
            'previous_adjustment_sha256':digest(previous),'restoration_adjustment_sha256':digest(current),
            'new_cash_or_shares_inferred':False,'source_rows_modified':False})
    return receipts


def development_gate(results):
    r=results.get('40',{})
    values=[r.get(k) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct')]
    return (r.get('status')=='RAW_DAILY_PROXY_RECONCILED'
        and all(type(v) in (int,float) and math.isfinite(v) for v in values)
        and min(values[:2])>0 and values[2]>=90 and r.get('account_sessions')==485
        and r.get('monthly_decisions')==24 and r.get('whole_day_volume_violations')==0
        and all(r.get(k) is True for k in ('all_fills_integer','daily_cash_and_share_conservation',
            'record_date_entitlements_verified','unverified_noncash_zero_ownership_verified')))


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
    p.add_argument('--source-preflight-only',action='store_true');a=p.parse_args(argv)
    root=Path(__file__).resolve().parents[1];base=Path(a.source_root);plan=Path(a.plan);out=Path(a.output_dir)
    if out.exists() or file_sha(plan)!=a.expected_plan_sha256:raise ValueError('fresh frozen physical diagnostic required')
    r=read(plan)
    if (r['status']!='FROZEN_ASSET_EXPANSION_RAW_DAILY_PRE2026' or r['candidate']!=CANDIDATE
            or r['initial_CNY']!='1000000' or r['extra_cost_bps']!=[20,40]
            or r['window']!=['2023-12-29','2025-12-31'] or r['protocol_file']!=PROTOCOL
            or set(r['method_code_sha256'])!=set(METHOD_FILES)):
        raise ValueError('fixed physical development scope and profiles required')
    bound={plan:a.expected_plan_sha256,root/PROTOCOL:r['protocol_sha256'],
        root/'experiments/qlib/audit_sources/2026-10-22-asset-expansion-primary-audit.py':r['primary_audit_code_sha256']}
    for field,directory in (('method_code_sha256',root),('public_inputs_sha256',root),('source_inputs_sha256',base)):
        for name,h in r[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('root-relative diagnostic input required')
            bound[directory/name]=h
    for f,h in bound.items():
        if file_sha(f)!=h:raise ValueError('frozen source/method changed: '+str(f))
    m=read(base/RAW/'manifest.json');qa=read(root/'experiments/qlib/asset-expansion-raw-source-audit.json')
    primary=read(root/'experiments/qlib/asset-expansion-primary-content-audit.json')
    if (qa['capture_manifest_sha256']!=file_sha(base/RAW/'manifest.json') or qa['names']!=36
            or qa['all_raw_packets_and_original_inputs_unchanged'] is not True
            or primary['status']!='THREE_ORIGINALS_HTTP_AND_SECOND_PDF_EXTRACTOR_CHECKED_NOT_ACCOUNT_ADMISSION'
            or primary['pages_read']!=11 or primary['cash_amounts_match_vendor'] is not True
            or primary['capital_tax_exemption_verified'] is not False):raise ValueError('separate technical and primary source evidence required')
    sessions=read(base/RAW/'calendar.json')['sessions']
    if len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=r['window']:
        raise ValueError('complete explicit development source calendar required')
    calendar=TradingCalendar(sessions);packets={};restorations=[]
    for code,h in m['per_code_sha256'].items():
        path=base/RAW/'codes'/(code+'.json')
        if file_sha(path)!=h:raise ValueError('raw packet changed')
        packet=read(path)
        if packet['instrument']!=code or packet['window']!=r['window'] or [v['date'] for v in packet['bars']]!=sessions:
            raise ValueError('fixed issuer/source window/calendar required')
        packets[code]=packet;restorations.extend(restoration_receipts(packet))
    if {(x['instrument'],x['restoration_day']) for x in restorations}!={('SH600535','2025-03-27'),('SH600737','2025-08-14')}:
        raise ValueError('only the two separately identified source restorations allowed')
    validate_source_coverage(packets)
    targets=read(base/TARGET)[CANDIDATE]
    if file_sha(base/TARGET)!=m['target_sha256'] or len(targets)!=24 or {c for t in targets.values() for c in t['weights']}!=set(packets):
        raise ValueError('unchanged complete primary targets required')
    docs=[]
    dates={'SH600535':'2025-03-20','SH600737':'2025-08-05','SH603688':'2024-05-16'}
    for d in primary['documents']:
        if file_sha(base/d['source_relative'])!=d['sha256']:raise ValueError('reviewed original PDF changed')
        docs.append({'instrument':d['instrument'],'day':dates[d['instrument']],'file':d['file'],'sha256':d['sha256']})
    proofs={'documents':docs,'cash_overrides':{},'capital_tax':{},'stock_dividend_tax_bases':{},'supplementary_distributions':[]}
    events,receipts=compile_distribution_events(packets,proofs,calendar)
    if len(events)!=79 or sum(x['requires_zero_record_ownership_if_tax_unverified'] for x in receipts)!=1:
        raise ValueError('complete79events and one unverified noncash constraint required')
    if a.source_preflight_only:print('36packets,79events,2restorations,24targets; no output or account returns');return 0
    bars={c:{v['date']:v for v in packet['bars']} for c,packet in packets.items()};out.mkdir(parents=True);results={}
    (out/'source_projection.json').write_text(json.dumps(clean({'events':[asdict(e) for e in events],
        'event_receipts':receipts,'restoration_receipts':restorations}),indent=2)+'\n')
    for bps in r['extra_cost_bps']:
        folder=out/str(bps);folder.mkdir();holders=[]
        def factory(cal,cash,distributions,**kw):
            account=StockDistributionAccount(cal,cash,distributions,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps),**kw)
            holders.append(account);return account
        try:
            print('physical daily primary',bps,'bp',flush=True)
            case=simulate_fixed_targets(calendar,bars,events,targets,r['initial_CNY'],lifecycles={},account_factory=factory,policy_id=CANDIDATE)
            if len(case['intents'])!=24 or case['lifecycle_source_audit']:raise ValueError('complete monthly decisions/no lifecycle source exceptions required')
            noncash=[e for e in events if e.capital_per_share>0 or e.stock_per_share>0];zero=[]
            for e in noncash:
                entries=[v for v in case['corporate_ledger'] if v['kind']=='EX_DATE_ENTITLEMENT' and v['event_id']==e.event_id]
                owned=case['ownership'][e.recorded.isoformat()].get(e.instrument,0)
                if len(entries)!=1 or owned!=0 or entries[0]['registered_quantity']!=0:raise ValueError('unverified noncash needs actual zero registered inventory')
                zero.append({'event_id':e.event_id,'instrument':e.instrument,'recorded':e.recorded.isoformat(),'actual_owned_shares':owned})
            days=[v for v in case['days'] if v['day']>='2024-01-02'];peak=Decimal(r['initial_CNY']);dd=Decimal(0)
            for v in days:peak=max(peak,v['equity']);dd=min(dd,v['equity']/peak-1)
            result={'status':'RAW_DAILY_PROXY_RECONCILED' if case['whole_day_volume_violations']==0 else 'INVALID_WHOLE_DAY_VOLUME',
                **summarize_case(case,r['initial_CNY']),'account_sessions':len(days),
                'average_exposure_pct':float(sum((v['exposure'] for v in days),Decimal(0))/len(days)*100),
                'max_drawdown_pct':float(dd*100),'two_year_return_pct':float((days[-1]['equity']/Decimal(r['initial_CNY'])-1)*100),
                'unverified_noncash_zero_ownership_verified':True,'zero_ownership_receipts':zero,'artifact_sha256':write_case(folder,case)}
        except (ValueError,KeyError,ArithmeticError) as exc:
            result={'status':'INVALID_ACCOUNT_OR_SOURCE','error_type':type(exc).__name__,'error':str(exc)}
            (folder/'error.json').write_text(json.dumps(result,indent=2)+'\n')
            if holders:
                ac=holders[0];(folder/'failed_account_state.json').write_text(json.dumps(clean({'last_clock':ac._last_clock,
                    'cash':ac.broker.cash,'positions':ac.broker.positions,'orders':ac.broker.orders,'fills':ac.broker.fills,
                    'corporate_ledger':ac.corporate_ledger,'cash_claims':ac.cash_claims,'stock_claims':ac.stock_claims}),indent=2)+'\n')
            result['failure_artifact_sha256']={f.name:file_sha(f) for f in folder.iterdir()}
        results[str(bps)]=result;(out/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
    changed=[str(f) for f,h in bound.items() if not f.is_file() or file_sha(f)!=h]
    summary={'status':'ASSET_EXPANSION_RAW_DAILY_DEVELOPMENT_COMPLETE','plan_sha256':a.expected_plan_sha256,
        'results_by_extra_bps':results,'changed_original_inputs':changed,
        'raw_daily_proxy_development_gate_passes':development_gate(results) and not changed,
        'execution':'unchanged prior-close integer sizing,next daily open,9.5percent reference limit proxy',
        'costs':'basebuy5bps/sell15bps,minCNY5 per fill,plus20/40bps extra separately rounded',
        'tax_model':'flat20percent cash stress reserve; not actualFIFOsettlement',
        'raw_account_independently_audited':False,'minute_execution_admitted':False,'historical_arrival_verified':False,
        'all_corporate_actions_independently_verified':False,'investment_factor_admitted':False,
        'new_2026_provider_queries':False,'2026_return_computed':False,'objective_achieved':False}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('physical daily gate',summary['raw_daily_proxy_development_gate_passes'],flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
