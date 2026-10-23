"""Separate raw evidence/primary-tail checker; imports no new capture producer."""
import argparse
from collections import Counter
from datetime import date
from pathlib import Path
import json

from scripts import audit_low_operating_raw_pre2026 as legacy
from scripts.audit_low_operating_raw_pre2026 import need,read,sha,inventory_files,resolve

START,END='2023-12-29','2025-12-31'
CANDIDATE='low_operating_profitability_followup_v1'
FAMILY='operating_profit_prior_assets_bottom_decile_control'
PDF='illiquidity-corporate-reviewed-20261020/SZ002505-delisting-announcement-20240830.pdf'
PDF_SHA='ef704fd9e654757548c8c36725edd22d726a6d7cf71de850b3096f315fe63e9b'
BOUNDARIES={'SZ002505':{'kind':'DELISTING_END','effective_date':'2024-08-30','verified_primary_boundary':True,
    'primary_document_sha256':PDF_SHA,'source_file':Path(PDF).name}}
INVENTORY='experiments/qlib/low-operating-lifecycle-source-inventory.json'
FAILURE='experiments/qlib/low-operating-profitability-raw-source-inventory-failure.json'
FAILURE_SHA='a27f135dcbfefc4db8005987bbc8f73a7e8ec6cfbb9ca3adcd0c3f4bc01f31b6'


def source_risk(packet,code,sessions,boundaries):
    need(boundaries==BOUNDARIES and sessions==sorted(set(sessions)),'independent original primary boundary required')
    observed=[r['date'] for r in packet['bars']]
    expected=[d for d in sessions if d<='2024-08-30'] if code=='SZ002505' else sessions
    need(observed==expected,'independent check: exact primary tail only; no interior/other gap')
    risk=legacy.packet_risks(packet,code,observed)
    intervals=[]
    if code=='SZ002505':
        for day in sessions:
            if day>='2024-08-30':intervals.append({'instrument':code,'session':day,'reason':'AT_OR_AFTER_PRIMARY_DELISTING_BOUNDARY',
                'original_row_present':day in observed,'primary_document_sha256':PDF_SHA,'synthetic_price_created':False})
    risk['lifecycle_coverage']={'full_explicit_calendar_covered':observed==sessions,'source_coverage_explained':True,
        'observed_rows':len(observed),'missing_sessions':[d for d in sessions if d not in observed],
        'lifecycle_intervals':intervals,'actual_flat_inventory_proven':False,'synthetic_source_rows_created':0}
    return risk


def audit(base,root,raw,request,expected):
    need(sha(request)==expected and (raw/'request.json').read_bytes()==request.read_bytes(),'frozen exact source request')
    r=read(request);inv=r['inventory'];need(r['status']=='FROZEN_LOW_OPERATING_PRIMARY_LIFECYCLE_SOURCE_CONTINUATION'
        and r['candidate']==CANDIDATE and r['target_family']==FAMILY and r['window']==[START,END]
        and len(r['codes'])==len(set(r['codes']))==43 and r['fresh_codes']==['SZ002326'] and len(r['reuse_routes'])==42
        and set(r['reuse_routes'])==set(r['codes'])-{'SZ002326'} and r['boundaries']==BOUNDARIES
        and r['maximum_new_query_reservations']==4 and r['max_attempts_per_query']==r['maximum_administrative_login_attempts']==1
        and r['socket_timeout_seconds']==20 and r['baostock_version']=='0.9.4'
        and r['portfolio_returns_permitted'] is False and r['2026_values_permitted'] is False,'independent fixed source scope')
    need(inv==read(root/INVENTORY) and sha(root/FAILURE)==FAILURE_SHA and inv['original_failure_sha256']==FAILURE_SHA,'preserved strict failure/new inventory')
    paths={k:resolve(k,root,base) for k in r['input_sha256']};paths['frozen_request']=request;want={**r['input_sha256'],'frozen_request':expected}
    for k,p in paths.items():need(sha(p)==want[k],'original source input before '+k)
    need(all(r['input_sha256'].get('repo/'+p)==h for p,h in r['method_sha256'].items()),'explicit method identities')
    need(sha(base/PDF)==PDF_SHA and r['input_sha256'].get('source/'+PDF)==PDF_SHA,'authenticated original delisting PDF')
    reviewed='illiquidity-corporate-reviewed-20261020/reviewed-manifest.json'
    need(sha(base/reviewed)=='d589c067f1498df1f6cffb810863751414155f05429dc44c934e5be861fa9ae4'
        and read(base/reviewed)['lifecycles']['SZ002505']==BOUNDARIES['SZ002505'],'exact previously reviewed primary literal')
    selected=read(root/'experiments/qlib/low-operating-profitability-continuation.json')
    need(selected['candidate']==CANDIDATE and selected['selected_from_seen_development_control'] is True
        and selected['fresh_independent_hypothesis'] is False and selected['original_primary_lead'] is None,'adaptive selection cannot replace original rejected primary')
    target=root/'experiments/qlib/operating-profitability-pre2026-targets.json';targets=read(target)[FAMILY]
    need(sha(target)==r['target_sha256']==selected['target_sha256'] and len(targets)==24
        and sorted({c for x in targets.values() for c in x['weights']})==r['codes']==inv['codes'],'all original target weights and formations')
    before=inventory_files(raw);m=read(raw/'manifest.json');terminal=read(raw/'followup-terminal.json')
    need(m['capture_complete'] is True and m['all_source_calendars_complete'] is False and m['names']==m['requested_names']==43
        and not m['errors_sha256'] and not m['pending_codes'] and m['request_sha256']==expected and m['target_sha256']==r['target_sha256']
        and terminal['complete'] is True and terminal['all_inputs_unchanged'] is True and terminal['candidate']==CANDIDATE
        and terminal['request_sha256']==expected and terminal['all_source_calendars_complete'] is False
        and terminal['shared_adapter_origin_status']==m['status']=='LOW_MARKET_RESIDUAL_VOL1M_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE','honest partial-calendar source terminal and original adapter identity')
    need(not any('failure' in Path(n).name or n.startswith('.followup') for n in before),'no incomplete/failure outer terminal')
    need(terminal['all_capture_outputs_unchanged'] is True and not terminal['changed_capture_outputs']
        and terminal['capture_output_sha256']=={k:h for k,h in before.items() if k!='followup-terminal.json'},'complete capture output tree protected through persistence')
    sessions=read(raw/'calendar.json')['sessions'];need(sha(raw/'calendar.json')==m['calendar_sha256'] and len(sessions)==486
        and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END]
        and sessions==[d for d in (base/legacy.CALENDAR).read_text().splitlines() if START<=d<=END],'exact original486source sessions')
    old=legacy.old_auditor(root);risk={};totals=Counter();overlaps=0;failure=read(root/FAILURE)
    for code in r['codes']:
        choices=inv['all_choices'][code];old_choices=failure['all_choices'][code]
        need(len(choices)==len(old_choices),'all original overlap choices remain registered');fps=[]
        for item,original_item in zip(choices,old_choices):
            origin=base/item['file'];need(item['file']==item['directory']+'/codes/'+code+'.json'
                and all(item[k]==original_item[k] for k in ('file','directory','packet_sha256','fingerprint'))
                and sha(origin)==item['packet_sha256']==r['input_sha256'].get('source/'+item['file']),'all original overlap identities')
            packet=read(origin);check=source_risk(packet,code,sessions,BOUNDARIES);fp=legacy.fingerprint(packet)
            need(fp==item['fingerprint'] and check['lifecycle_coverage']==item['coverage'],'all raw economic/lifecycle overlap evidence')
            fps.append(fp);overlaps+=1
        need(len(set(fps))<=1,'all overlap prices/actions agree')
        p=raw/'codes'/(code+'.json');need(sha(p)==m['per_code_sha256'][code],'captured packet exact hash');packet=read(p)
        if code in r['reuse_routes']:
            route=r['reuse_routes'][code];need(choices and route==choices[0] and p.read_bytes()==(base/route['file']).read_bytes(),'42deterministic byte copies')
        else:need(code=='SZ002326' and not choices,'only fresh original code');old.journal_packet(raw,code,packet,expected)
        risk[code]=source_risk(packet,code,sessions,BOUNDARIES)
        need(risk[code]['lifecycle_coverage']==terminal['source_coverage'][code],'independent source coverage equals terminal')
        for k,f in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):totals[k]+=len(packet[f])
    need(overlaps==87 and set(m['per_code_sha256'])==set(r['codes']) and dict(totals)==m['totals'],'all43packets/87overlaps/raw totals')
    need(len(list(raw.rglob('reserved-*.json')))==len(list(raw.rglob('response-*.json')))==m['query_reservations_consumed']==4,'four response envelopes/reservations')
    login,logout=read(raw/'login-response-1.json'),read(raw/'logout-response-1.json')
    need(login['error_code']==logout['error_code']=='0' and len(list(raw.glob('login-reserved-*.json')))==1,'one successful login/cleanup')
    for value in (m,terminal,selected):
        for key in ('historical_arrival_verified','corporate_action_completeness_verified','actual_flat_inventory_proven',
                    'physical_account_admitted','portfolio_return_computed','2026_values_read','objective_achieved'):
            if key in value:need(value[key] is False,'source-only classifications cannot admit accounts/returns')
    for k,p in paths.items():need(sha(p)==want[k],'original source input after '+k)
    need(inventory_files(raw)==before,'all raw outputs unchanged')
    return {'status':'PASS_SEPARATE_LOW_OPERATING_43_SOURCES_WITH_PRIMARY_TAIL_NOT_ACCOUNT_ADMISSION','candidate':CANDIDATE,
        'request_sha256':expected,'audit_code_sha256':sha(Path(__file__)),'names':43,'reused_original_packets':42,
        'registered_overlap_packets_checked':87,'fresh_response_envelopes_redecoded':4,'totals':dict(totals),'source_risks':risk,
        'all_input_sha256':want,'all_capture_sha256':before,'all_inputs_outputs_unchanged':True,'no_new_producer_imports':True,
        'same_researcher_and_shared_legacy_risk_and_envelope_helpers':True,'historical_arrival_verified':False,
        'corporate_action_completeness_verified':False,'actual_flat_inventory_proven':False,'physical_account_admitted':False,
        'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','raw-dir','request','expected-request-sha256','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();target=Path(a.output);raw=Path(a.raw_dir).resolve();need(not target.exists() and not target.resolve().is_relative_to(raw),'fresh external proof only')
    try:result=audit(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],raw,Path(a.request).resolve(),a.expected_request_sha256)
    except BaseException as exc:
        with target.open('x') as f:json.dump({'status':'FAILED_SEPARATE_LOW_OPERATING_PRIMARY_TAIL_SOURCE_CHECK','error_type':type(exc).__name__,'error':str(exc),'objective_achieved':False},f,indent=2)
        raise
    with target.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(result['status'],result['totals'],flush=True)


if __name__=='__main__':main()
