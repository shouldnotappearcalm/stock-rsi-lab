"""Source-only complete frozen-prefix admission, no portfolio replay."""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from scripts.illiquidity_minute_sources import authenticate_reused_minutes,prefix_minute_requirements
from scripts.prepare_illiquidity_account_events import METHOD_FILES as SOURCE_METHODS,authenticate_sources
from scripts.run_low_risk_intraday_replay import METHOD_FILES as MINUTE_METHODS,TapeBank
from scripts.tdx_history_checks import inspect_minutes


METHOD_FILES=tuple(dict.fromkeys((*SOURCE_METHODS,*MINUTE_METHODS,
    "scripts/admit_illiquidity_minutes_pre2026.py","scripts/illiquidity_minute_sources.py",
    "scripts/fundamental_query_journal.py","scripts/prepare_qlib_master_market_pre2026.py")))

def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('base-dir','raw-data-dir','proof-dir','targets','request','extra-tape-dir','output-dir'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1]
    base,raw,proofdir,targetsfile,requestfile,extra,out=map(Path,(args.base_dir,args.raw_data_dir,args.proof_dir,args.targets,args.request,args.extra_tape_dir,args.output_dir))
    if out.exists():raise ValueError('minute admission output already exists')
    request=json.loads(requestfile.read_text());manifest=json.loads((extra/'manifest.json').read_text())
    plan=json.loads((root/'experiments/qlib/illiquidity-minute-development-capture-plan.json').read_text())
    if (file_sha(requestfile)!=plan['request_sha256'] or manifest['request_sha256']!=plan['request_sha256']
            or file_sha(extra/'plan.json')!=file_sha(root/'experiments/qlib/illiquidity-minute-development-capture-plan.json')
            or manifest['plan_sha256']!=file_sha(extra/'plan.json')
            or manifest['complete_capture'] is not True or manifest['captured']!=manifest['requested']
            or manifest['captured']!=len(request['supplemental_requests'])):
        raise ValueError('complete frozen supplemental minute capture required')
    for name,h in request['source_manifest_sha256'].items():
        if Path(name).name!=name or file_sha(base/name/'manifest.json')!=h:raise ValueError('original minute source manifest changed')
    packets,proof,calendar=authenticate_sources(raw,proofdir,targetsfile,root)
    if file_sha(raw/'manifest.json')!=plan['raw_manifest_sha256'] or file_sha(proofdir/'reviewed-manifest.json')!=plan['proof_manifest_sha256']:
        raise ValueError('raw/proof identity differs from minute capture')
    bars={code:{r['date']:r for r in p['bars']} for code,p in packets.items()}
    active,skipped=prefix_minute_requirements(json.loads(targetsfile.read_text()),bars,proof['lifecycles'])
    if active!=request['active_requests'] or skipped!=request['nonexecuting_source_intervals']:
        raise ValueError('frozen active/nonexecuting source prefix changed')
    expected={c+'-'+d+'.json' for c,d in request['supplemental_requests']}
    if set(manifest['per_session_sha256'])!=expected:raise ValueError('supplemental minute key coverage changed')
    old=base/request['primary_tape_root'];bank=TapeBank(old,extra,bars,'2025-12-31')
    authenticated_reuse={fn:{'root':request['primary_tape_root'],'sha256':h}
        for fn,h in json.loads((old/'manifest.json').read_text())['per_session_sha256'].items()}
    authenticate_reused_minutes(base,authenticated_reuse,active)
    rows=[]
    for number,(code,day) in enumerate(active,1):
        row={'instrument':code,'day':day};path,h=bank.index[(code,day)]
        if file_sha(path)!=h:raise ValueError('minute source packet bytes changed')
        packet=json.loads(path.read_text());record=packet.get('methods',{}).get('minutes.history',packet)
        if packet['instrument']!=code or packet['requested_day']!=day:raise ValueError('minute security/session changed')
        row.update(source_sha256=h,captured_status=record['status'])
        try:
            windows=bank(code,date.fromisoformat(day))
            row.update(status='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE',windows=len(windows),
                facts=inspect_minutes(code,day,record['response'],bars[code][day]))
        except (ValueError,KeyError,AssertionError) as exc:
            row.update(status='SOURCE_REJECTED',error=str(exc))
        rows.append(row)
        if number%500==0:print('source admission '+str(number)+'/'+str(len(active)),flush=True)
    counts=dict(Counter(r['status'] for r in rows));out.mkdir(parents=True)
    details={'sessions':rows,'nonexecuting_source_intervals':skipped}
    (out/'details.json').write_text(json.dumps(details,indent=2)+'\n')
    result={'status':'ILLIQUIDITY_PRE2026_MINUTE_SOURCE_ADMISSION_COMPLETE',
        'audit_code_sha256':file_sha(Path(__file__)),
        'method_code_sha256':{n:file_sha(root/n) for n in METHOD_FILES},'request_sha256':file_sha(requestfile),
        'raw_manifest_sha256':file_sha(raw/'manifest.json'),'proof_manifest_sha256':file_sha(proofdir/'reviewed-manifest.json'),
        'old_tape_manifest_sha256':file_sha(old/'manifest.json'),'extra_tape_manifest_sha256':file_sha(extra/'manifest.json'),
        'required_active_sessions':len(active),'nonexecuting_source_intervals':len(skipped),'status_counts':counts,
        'full_series_labels_prices_ranges_and_stressed_volume_checked':True,
        'admitted_for_reconstructed_execution':counts.get('SOURCE_REJECTED',0)==0,
        'local_detail_sha256':file_sha(out/'details.json'),
        'source_volume_unit':'hands; conservative lower-share capacity checked; exact share precision not certified',
        'historical_arrival_verified':False,'sdk_date_echo_authenticated':False,'queue_and_impact_calibrated':False,
        'actual_record_date_entitlements_verified':False,'actual_delisting_exit_verified':False,
        'portfolio_returns_computed':False,'2026_market_values_queried':False,'objective_achieved':False,
        'exceptions':[r for r in rows if r['status']!='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE']}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
