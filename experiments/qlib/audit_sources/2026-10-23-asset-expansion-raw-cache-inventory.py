"""Opaque packet hashes and manifest windows only; no raw bar/action decoding."""
import argparse,hashlib,json
from pathlib import Path


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','target-summary','target-summary-sha256','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();base,target,out=map(Path,(a.source_root,a.target_summary,a.output))
    if out.exists() or sha(target)!=a.target_summary_sha256:raise ValueError('fresh inventory and exact fixed target union')
    summary=json.loads(target.read_text());codes=summary['primary_target_union']
    if codes!=sorted(set(codes)) or len(codes)!=47 or summary['completed_formations']!=34:raise ValueError('same complete47-name target dependency scope')
    inputs={str(target):sha(target)};rows={c:[] for c in codes};manifests={}
    for folder in sorted(base.iterdir()):
        manifest=folder/'manifest.json'
        if 'raw' not in folder.name or not folder.is_dir() or not manifest.is_file():continue
        before=sha(manifest);m=json.loads(manifest.read_text());hashes=m.get('per_code_sha256')
        if not isinstance(hashes,dict) or not set(codes)&set(hashes):continue
        inputs[str(manifest)]=before;manifests[folder.name]={'manifest_sha256':before,'status':m.get('status'),'window':m.get('window')}
        for c in sorted(set(codes)&set(hashes)):
            packet=folder/'codes'/(c+'.json');actual=sha(packet) if packet.is_file() else None
            if actual is not None:inputs[str(packet)]=actual
            rows[c].append({'cache':folder.name,'manifest_window':m.get('window'),
                'packet_sha256_in_manifest':hashes[c],'actual_opaque_packet_sha256':actual,
                'packet_present_and_byte_matched':actual==hashes[c],
                'bar_action_schema_and_actual_coverage_verified':False,'source_admitted_for_replay':False})
    latest={}
    for c,candidates in rows.items():
        ends=[r['manifest_window'][1] for r in candidates if r['packet_present_and_byte_matched'] and
            type(r['manifest_window']) is list and len(r['manifest_window'])==2 and r['manifest_window'][0]<='2023-12-29']
        latest[c]=max(ends) if ends else None
    for name,h in inputs.items():
        if not Path(name).is_file() or sha(Path(name))!=h:raise ValueError('original metadata/opaque packet changed during inventory')
    result={'status':'METADATA_ONLY_RAW_CACHE_INVENTORY_NOT_SOURCE_ADMISSION','inventory_code_sha256':sha(Path(__file__)),
        'target_summary_sha256':a.target_summary_sha256,'primary_target_names':47,'manifest_cache_count':len(manifests),
        'cache_manifests':manifests,'all47_dependency_candidates':rows,'latest_advertised_byte_matched_window_end':latest,
        'names_with_advertised_prefix_through_2026_10_20':sum(v is not None and v>='2026-10-20' for v in latest.values()),
        'names_with_advertised_prefix_through_2026_10_16':sum(v is not None and v>='2026-10-16' for v in latest.values()),
        'names_with_advertised_prefix_through_2026_10_21':sum(v is not None and v>='2026-10-21' for v in latest.values()),
        'names_with_any_byte_matched_prefix':sum(v is not None for v in latest.values()),
        'all_consumed_original_file_sha256':inputs,'original_files_unchanged':True,'source_admitted_for_replay':False,
        'raw_bar_or_distribution_values_decoded':False,'source_queries':0,'portfolio_returns_computed':False,'objective_achieved':False}
    with out.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
    print('Metadata-only47-name inventory: caches',len(manifests),'; advertisedOct20',result['names_with_advertised_prefix_through_2026_10_20'],
        ';Oct16',result['names_with_advertised_prefix_through_2026_10_16'],';Oct21',result['names_with_advertised_prefix_through_2026_10_21'],
        ';any prefix',result['names_with_any_byte_matched_prefix'])


if __name__=='__main__':main()
