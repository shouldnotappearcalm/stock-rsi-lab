"""Authenticate frozen pre2026 sources and compile events, never portfolio ROI.

Lifecycle intervals below are source classifications only. An actual replay
must still prove zero inventory, pending shares, orders and price dependencies.
"""
import argparse
import copy
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path

from scripts.capture_frozen_target_development_data import START,END,target_codes
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_low_risk_raw_share_validation import clean,validate_source_coverage
from stock_rsi.broker import money
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.lifecycle_source_rows import source_rows_on

METHOD_FILES=('scripts/prepare_illiquidity_account_events.py','src/stock_rsi/distribution_event_compiler.py',
    'src/stock_rsi/lifecycle_source_rows.py','src/stock_rsi/stock_distribution_account.py',
    'scripts/run_low_risk_raw_share_validation.py','scripts/capture_frozen_target_development_data.py',
    'src/stock_rsi/raw_share_account.py','src/stock_rsi/calendar.py','src/stock_rsi/broker.py',
    'src/stock_rsi/data.py','src/stock_rsi/time.py')


def authenticate_sources(raw,proofdir,targets_file,root):
    public=root/'experiments/qlib'
    for source,frozen in ((raw/'manifest.json',public/'illiquidity-raw-source-capture-manifest.json'),
            (proofdir/'reviewed-manifest.json',public/'illiquidity-corporate-reviewed-manifest.json'),
            (proofdir/'capture-manifest.json',public/'illiquidity-corporate-capture-manifest.json')):
        if sha256_file(source)!=sha256_file(frozen):raise ValueError('frozen source manifest changed')
    manifest=json.loads((raw/'manifest.json').read_text());proof=json.loads((proofdir/'reviewed-manifest.json').read_text())
    if (proof['raw_manifest_sha256']!=sha256_file(raw/'manifest.json')
            or proof['capture_manifest_sha256']!=sha256_file(proofdir/'capture-manifest.json')
            or proof['target_sha256']!=manifest['target_sha256']
            or sha256_file(targets_file)!=manifest['target_sha256']
            or sha256_file(raw/'calendar.json')!=manifest['calendar_sha256']):
        raise ValueError('frozen source, calendar or target provenance changed')
    documents={d['file']:d for d in proof['documents']}
    if len(documents)!=len(proof['documents']):raise ValueError('duplicate primary document')
    for name,doc in documents.items():
        if Path(name).name!=name or doc['day']>END or sha256_file(proofdir/name)!=doc['sha256']:
            raise ValueError('primary source document changed')
    for code,boundary in proof['lifecycles'].items():
        document=documents[boundary['source_file']]
        if document['instrument']!=code or document['sha256']!=boundary['primary_document_sha256']:
            raise ValueError('lifecycle primary source binding changed')
    sessions=json.loads((raw/'calendar.json').read_text())['sessions']
    if sessions!=sorted(set(sessions)) or sessions[0]!=START or sessions[-1]!=END:
        raise ValueError('explicit full development calendar required')
    calendar=TradingCalendar(sessions);targets=json.loads(targets_file.read_text());codes=target_codes(targets)
    if set(codes)!=set(manifest['per_code_sha256']):raise ValueError('full fixed target source universe required')
    packets={}
    for code in codes:
        path=raw/'codes'/(code+'.json')
        if sha256_file(path)!=manifest['per_code_sha256'][code]:raise ValueError('frozen raw source packet changed')
        packet=json.loads(path.read_text());days=[r['date'] for r in packet['bars']]
        if (packet['instrument']!=code or packet['window']!=[START,END] or days!=sorted(set(days))
                or not set(days)<=set(sessions)):
            raise ValueError('raw source identity or session coverage changed')
        packets[code]=packet
    return packets,proof,calendar


def classify_source_coverage(packets,proof,calendar):
    """No entitlement sizes come from factors; retain every original source row."""
    merged=copy.deepcopy(packets)
    for item in proof['supplementary_distributions']:
        merged[item['instrument']]['distributions'].append(copy.deepcopy(item['record']))
    initial=[]
    for code,packet in merged.items():
        boundary=proof['lifecycles'].get(code,{})
        if boundary.get('kind')!='LISTING_BEGIN':continue
        effective=boundary['effective_date']
        if packet['bars'][0]['date']!=effective:raise ValueError('IPO source does not begin at certified first session')
        candidates=[a for a in packet['adjustments'] if a['dividOperateDate']==effective]
        if len(candidates)!=1:raise ValueError('unique initial IPO normalization record required')
        a=candidates[0]
        if (money(a['backAdjustFactor'])!=1 or money(a['adjustFactor'])!=1
                or money(a['foreAdjustFactor'])<=0
                or any(r['dividOperateDate']==effective for r in packet['distributions'])):
            raise ValueError('IPO normalization needs separate evidence; not a distribution')
        initial.append({'instrument':code,'effective_date':effective,'source_adjustment':copy.deepcopy(a),
            'primary_document_sha256':boundary['primary_document_sha256'],
            'classification':'INITIAL_LISTING_NORMALIZATION_NOT_DISTRIBUTION',
            'factor_used_to_infer_cash_or_shares':False})
        packet['adjustments']=[item for item in packet['adjustments'] if item is not a]
    validate_source_coverage(merged)
    bars={code:{row['date']:row for row in packet['bars']} for code,packet in packets.items()}
    lifecycle=[]
    for day in calendar.days:
        _,exceptions=source_rows_on(bars,day,(),proof['lifecycles']);lifecycle.extend(exceptions)
    return initial,lifecycle


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('raw-data-dir','proof-dir','targets','output-dir'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
    if out.exists():raise ValueError('source-event output already exists')
    raw,proofdir,targets=map(Path,(args.raw_data_dir,args.proof_dir,args.targets))
    packets,proof,calendar=authenticate_sources(raw,proofdir,targets,root)
    events,receipts=compile_distribution_events(packets,proof,calendar)
    initial,lifecycle=classify_source_coverage(packets,proof,calendar)
    out.mkdir(parents=True)
    artifacts={}
    for name,value in (('derived_events.json',clean([asdict(e) for e in events])),
            ('event_source_receipts.json',receipts),('initial_listing_classification.json',initial),
            ('lifecycle_source_intervals.json',lifecycle)):
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');artifacts[name]=sha256_file(out/name)
    result={'status':'PRE2026_SOURCE_EVENTS_COMPILED_REAL_ACCOUNT_ADMISSION_PENDING',
        'raw_manifest_sha256':sha256_file(raw/'manifest.json'),'reviewed_manifest_sha256':sha256_file(proofdir/'reviewed-manifest.json'),
        'target_sha256':sha256_file(targets),'method_code_sha256':{n:sha256_file(root/n) for n in METHOD_FILES},
        'source_distribution_count':sum(len(p['distributions']) for p in packets.values()),
        'primary_supplement_count':len(proof['supplementary_distributions']),'compiled_event_count':len(events),
        'stock_dividend_events':sum(e.stock_per_share>0 for e in events),
        'capital_transfer_events':sum(e.capital_per_share>0 for e in events),
        'capital_events_requiring_actual_zero_ownership_or_additional_proof':sum(r['requires_zero_record_ownership_if_tax_unverified'] for r in receipts),
        'source_interval_classifications':len(lifecycle),'original_missing_rows':sum(not r['original_row_present'] for r in lifecycle),
        'initial_listing_normalizations':len(initial),'artifact_sha256':artifacts,
        'source_packets_modified':False,'synthetic_price_rows_created':False,
        'actual_record_date_entitlements_verified':False,'actual_delisting_exit_verified':False,
        'real_portfolio_runner_integration_complete':False,'intraday_source_admission_complete':False,
        'admitted_for_account_replay':False,'portfolio_returns_computed':False,'2026_market_values_queried':False,'objective_achieved':False}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
