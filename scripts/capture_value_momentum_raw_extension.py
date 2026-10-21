"""One frozen foreground composite raw-source capture; source-only preflight available."""
import argparse
import json
import socket
from importlib.metadata import version
from pathlib import Path
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.value_momentum_raw_extension_sources import (
    START,PRE_END,END,MAX_QUERIES,SourceSession,baseline_from_cache,capture_packets,
    compose_packet,expected_sessions,partition,validate_bars,verify_overlap,
)

SOURCES=('low-beta60-raw-horizon-20261021','low-risk-raw-account-data-20261017','szse-value-raw-full-20261017','reversal-raw-full-20261017')
FORM='szse-value-momentum-formations-full-v2-20261021'
OLD='szse-value-momentum-raw-dev-20261021'
PROJECTION='szse-value-momentum-account-sources-20261021'
INVENTORY='experiments/qlib/szse-value-momentum-full-raw-inventory.json'
PROTOCOL='docs/research/szse-value-momentum-raw-extension-source-plan-2026-10-21.md'
METHOD_FILES=('scripts/capture_value_momentum_raw_extension.py','scripts/value_momentum_raw_extension_sources.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/capture_low_risk_raw_account_data.py',
 'scripts/capture_illiquidity_raw_development.py','scripts/fundamental_query_journal.py',
 'scripts/capture_frozen_target_development_data.py',
 'experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-full-raw-inventory.py')
PUBLIC_FILES=('experiments/qlib/szse-value-momentum-2026-target-v2-verification.json',
 'experiments/qlib/szse-value-momentum-2026-target-v2-independent-audit.json',
 'experiments/qlib/szse-value-momentum-2026-target-v2-receipt.json',
 'experiments/qlib/szse-value-momentum-2026-targets.json',INVENTORY,
 'experiments/qlib/szse-value-momentum-full-raw-inventory-review.json',PROTOCOL)
LOCAL_FILES=(OLD+'/manifest.json',OLD+'/calendar.json',PROJECTION+'/summary.json',PROJECTION+'/lifecycles.json',
 FORM+'/targets.json',FORM+'/receipt.json','szse-value-momentum-full-raw-inventory-20261021.json')
OUTPUT='szse-value-momentum-raw-full-20261021'

def read(path):return json.loads(Path(path).read_text())
def relative(root,name):
    if not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('safe relative frozen path required')
    return root/name

def authenticate_request(path,expected_sha,repo,base):
    repo,base=Path(repo),Path(base)
    if sha256_file(path)!=expected_sha:raise ValueError('frozen request changed')
    r=read(path)
    if (r['status']!='FROZEN_COMPOSITE_RAW_EXTENSION_SOURCE_REQUEST' or r['candidate']!='szse_value_momentum_equal'
        or r['window']!=[START,END] or r['maximum_source_reservations']!=MAX_QUERIES
        or r['max_attempts_per_query']!=1 or r['maximum_consecutive_failed_codes']!=3
        or r['maximum_administrative_login_attempts']!=1 or r['socket_timeout_seconds']!=20
        or r['output_directory']!=OUTPUT or r['protocol_file']!=PROTOCOL):raise ValueError('fixed protocol or budget changed')
    for field,files,parent in (('method_code_sha256',METHOD_FILES,repo),('public_evidence_sha256',PUBLIC_FILES,repo),('local_source_sha256',LOCAL_FILES,base)):
        if set(r[field])!=set(files):raise ValueError('exact frozen file set required: '+field)
        for name,h in r[field].items():
            if sha256_file(relative(parent,name))!=h:raise ValueError('frozen method/source/evidence changed: '+name)
    inv=read(repo/INVENTORY);verification=read(repo/PUBLIC_FILES[0]);audit=read(repo/PUBLIC_FILES[1])
    if ((repo/INVENTORY).read_bytes()!=(base/LOCAL_FILES[-1]).read_bytes()
        or inv['source_priority_fixed_before_inventory']!=list(SOURCES)
        or inv['cross_cache_raw_core_conflict_codes'] or inv['original_pre2026_prefix_conflict_codes']
        or not all(inv['semantic_negative_controls_passed'].values())
        or verification['all34formations_independently_reconstructed'] is not True
        or verification['old24target_and_receipt_bytes_identical'] is not True
        or verification['independent_audit_sha256']!=sha256_file(repo/PUBLIC_FILES[1])
        or audit['all_three_families_34_targets_reconstructed'] is not True
        or audit['original24_complete_receipts_and_family_targets_byte_exact'] is not True
        or audit['imports_project_code'] is not False or not all(audit['semantic_negative_controls_rejected'].values())):
        raise ValueError('original target/source independent checks missing')
    target=base/FORM/'targets.json';receipt=read(base/FORM/'receipt.json')
    if (sha256_file(target)!=r['target_sha256'] or r['target_sha256']!=inv['target_sha256']
        or receipt['artifact_sha256']['targets.json']!=r['target_sha256']
        or audit['receipt_sha256']!=sha256_file(base/FORM/'receipt.json')
        or (repo/PUBLIC_FILES[2]).read_bytes()!=(base/FORM/'receipt.json').read_bytes()
        or (repo/PUBLIC_FILES[3]).read_bytes()!=target.read_bytes()):raise ValueError('target/receipt byte identities changed')
    targets=read(target);codes=sorted({c for t in targets.values() for c in t['weights']})
    if codes!=r['codes'] or len(codes)!=127 or len(targets)!=34:raise ValueError('complete127name34target scope required')
    if set(r['source_manifest_sha256'])!=set(SOURCES) or set(r['source_calendar_sha256'])!=set(SOURCES):raise ValueError('all four sources required')
    manifests={}
    for name in SOURCES:
        folder=base/name
        if sha256_file(folder/'manifest.json')!=r['source_manifest_sha256'][name] or r['source_manifest_sha256'][name]!=inv['source_manifest_sha256'][name]:raise ValueError('cache manifest changed')
        manifests[name]=read(folder/'manifest.json')
        if sha256_file(folder/'calendar.json')!=r['source_calendar_sha256'][name] or r['source_calendar_sha256'][name]!=inv['source_calendar_sha256'][name] or manifests[name]['calendar_sha256']!=r['source_calendar_sha256'][name]:raise ValueError('cache calendar changed')
    sessions=[d for d in read(base/SOURCES[0]/'calendar.json')['sessions'] if START<=d<=END]
    if sessions!=sorted(set(sessions)) or len(sessions)!=676 or [sessions[0],sessions[-1]]!=[START,END]:raise ValueError('676 explicit sessions required')
    if [d for d in sessions if d<=PRE_END]!=read(base/OLD/'calendar.json')['sessions']:raise ValueError('original calendar prefix changed')
    for name in SOURCES:
        end=min(END,manifests[name]['window'][1]);observed=[d for d in read(base/name/'calendar.json')['sessions'] if START<=d<=end]
        if observed!=[d for d in sessions if d<=end]:raise ValueError('cache calendar disagrees with source reference')
    old=read(base/OLD/'manifest.json');ss=read(base/PROJECTION/'summary.json');life=read(base/PROJECTION/'lifecycles.json')
    if (sha256_file(base/OLD/'manifest.json')!=inv['original_pre2026_manifest_sha256']
        or sha256_file(base/PROJECTION/'summary.json')!=inv['source_projection_summary_sha256']
        or sha256_file(base/PROJECTION/'lifecycles.json')!=inv['lifecycle_sha256']
        or ss['artifact_sha256']['lifecycles.json']!=inv['lifecycle_sha256']
        or old['per_code_sha256']!=r['original_packet_sha256'] or len(old['per_code_sha256'])!=103
        or set(life)!= {'SZ001389'} or life['SZ001389']['effective_date']!='2024-04-02'
        or life['SZ001389']['verified_primary_boundary'] is not True):raise ValueError('original103/primary listing boundary changed')
    baselines={};lineage={};lifecycles={'SZ001389':'2024-04-02'}
    for c,h in old['per_code_sha256'].items():
        f=base/OLD/'codes'/(c+'.json')
        if sha256_file(f)!=h:raise ValueError('old packet changed')
        v=read(f)
        if v['instrument']!=c or v['window']!=[START,PRE_END] or [x['date'] for x in v['bars']]!=[d for d in expected_sessions(c,sessions,lifecycles.get(c)) if d<=PRE_END]:raise ValueError('old prefix calendar/identity changed')
        baselines[c]=v;lineage[c]={'baseline':{'kind':'ORIGINAL_DEVELOPMENT_PACKET','file':str(f.relative_to(base)),'sha256':h}}
    cached={};overlaps={};routes={}
    for c in codes:
        item=inv['items'][c];choices=item['choices'];payloads=[];proofs=[]
        if item['cross_cache_core_conflict'] or item['original_prefix_conflict']:raise ValueError('unreviewed cache conflict')
        for choice in choices:
            name=choice['source_directory']
            if name not in SOURCES:raise ValueError('unregistered cache directory')
            h=choice['source_packet_sha256'];f=base/name/'codes'/(c+'.json')
            if manifests[name]['per_code_sha256'][c]!=h or sha256_file(f)!=h:raise ValueError('registered cache packet changed')
            v=read(f)
            if v['instrument']!=c or v['window']!=choice['window']:raise ValueError('registered cache identity changed')
            validate_bars(c,[r for r in v['bars'] if START<=r['date']<=END])
            expected=[d for d in expected_sessions(c,sessions,lifecycles.get(c)) if d<=min(END,v['window'][1])]
            if [x['date'] for x in v['bars'] if START<=x['date']<=END]!=expected:raise ValueError('registered cache has unexplained gaps')
            for previous in payloads:verify_overlap(v,previous)
            if c in baselines:verify_overlap(baselines[c],v)
            payloads.append(v);proofs.append({'source_directory':name,'source_packet_sha256':h,'source_window':v['window'],
                'original_provenance':v.get('provenance'),'original_source_query_receipts':v.get('source_query_receipts')})
        if not choices:
            if item['priority_route'] is not None:raise ValueError('empty cache route changed')
            continue
        first=choices[0]
        if item['priority_route']!=first['source_directory']:raise ValueError('priority route changed')
        routes[c]={'source_directory':first['source_directory'],'source_packet_sha256':first['source_packet_sha256'],'complete_through_Oct20':first['complete_through_Oct20']}
        overlaps[c]=payloads;lineage.setdefault(c,{})['registered_caches']=proofs
        if c not in baselines:
            baselines[c]=baseline_from_cache(c,payloads[0],sessions)
            lineage[c]['baseline']={'kind':'CLIPPED_NEW_NAME_PRE2026_CACHE','source_directory':first['source_directory'],'source_packet_sha256':first['source_packet_sha256']}
        if first['complete_through_Oct20']:
            compose_packet(c,payloads[0],baselines[c],sessions,caches=payloads,listed_on=lifecycles.get(c));cached[c]=payloads[0]
    route=partition(codes,baselines,cached)
    if (routes!=r['cache_routes'] or sorted(baselines)!=r['baseline_codes'] or route['fresh']!=r['fresh_codes']
        or len(cached)!=15 or len(baselines)!=114 or len(route['incremental'])!=99 or len(route['cold'])!=13 or route['budget']!=362):raise ValueError('derived362query partition changed')
    return r,codes,sessions,baselines,cached,overlaps,lifecycles,lineage

def verify_postcapture(out,authenticate):
    record={'source_inputs_unchanged_after_capture':False}
    try:authenticate()
    except Exception as exc:record.update(error_type=type(exc).__name__,error=str(exc))
    else:record['source_inputs_unchanged_after_capture']=True
    atomic_json(Path(out)/'source-postcheck.json',record)
    return record

def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256','output-dir'):p.add_argument('--'+n,required=True)
    p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv)
    out=Path(a.output_dir);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1]
    if out.exists():raise ValueError('preserve existing output; no resume')
    r,codes,sessions,baselines,cached,overlaps,lifecycles,lineage=authenticate_request(a.request,a.expected_request_sha256,repo,base)
    if out.resolve()!=(base/OUTPUT).resolve() or version('baostock')!=r['baostock_version']:raise ValueError('fixed output or SDK version changed')
    if a.preflight_only:print('source preflight127names/15full/99incremental/13cold/362queries; no source connection or output');return 0
    import baostock as sdk
    socket.setdefaulttimeout(20);session=SourceSession(out,a.expected_request_sha256,sdk)
    interrupted=False
    try:
        manifest=capture_packets(out,codes,sessions,baselines,cached,a.expected_request_sha256,session,
            overlaps=overlaps,lifecycles=lifecycles,lineage=lineage,request_bytes=Path(a.request).read_bytes())
    except BaseException:
        interrupted=True;raise
    finally:
        if out.exists():
            session.close()
            checked=verify_postcapture(out,lambda:authenticate_request(a.request,a.expected_request_sha256,repo,base))
            if (out/'manifest.json').exists():
                m=read(out/'manifest.json');m.update(cleanup_sha256=sha256_file(out/'cleanup.json'),method_code_sha256=r['method_code_sha256'],
                    target_sha256=r['target_sha256'],original_packet_sha256=r['original_packet_sha256'],cache_routes=r['cache_routes'],
                    source_manifest_sha256=r['source_manifest_sha256'],source_calendar_sha256=r['source_calendar_sha256'],
                    source_inputs_unchanged_after_capture=checked['source_inputs_unchanged_after_capture'],
                    source_postcheck_sha256=sha256_file(out/'source-postcheck.json'),
                    original_source_files_changed=False if checked['source_inputs_unchanged_after_capture'] else None,
                    SDK_decoded_responses_not_TCP_wire=True,full_October_complete=False,
                    source_units={'price':'CNY/share','volume':'shares','amount':'CNY'})
                atomic_json(out/'manifest.json',m)
            if not interrupted and not checked['source_inputs_unchanged_after_capture']:
                raise ValueError('postcapture source authentication failed; artifacts preserved')
    return 0 if manifest['names']==len(codes) else 2
if __name__=='__main__':raise SystemExit(main())
