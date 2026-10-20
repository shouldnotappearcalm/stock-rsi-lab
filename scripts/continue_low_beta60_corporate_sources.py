"""Continue two title-parser failures using saved listings; never repeat APIs."""
import argparse
import base64
import fcntl
import json
import re
import time
from pathlib import Path

from scripts.audit_cninfo_report_admission import query
from scripts.capture_budgeted_corporate_notices_pre2026 import journaled_bytes,read_wire
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.fundamental_query_journal import QueryJournal,digest,write_packet_once

METHOD_FILES=('scripts/continue_low_beta60_corporate_sources.py',
 'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/audit_cninfo_report_admission.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py')


def select_implementation_notice(rows,case):
    code=case['instrument'][2:];day=case['publication_day']
    if not '2024-01-01'<=day<='2025-12-31':raise ValueError('pre2026 publication required')
    matches=[r for r in rows if r['code']==code and r['day']==day
        and re.search('(?:权益分派|利润分配)实施(?:的)?公告',r['title'])]
    if len(matches)!=1:raise ValueError('unique original implementation announcement required')
    row=matches[0]
    if (not re.fullmatch('[0-9]+',row['announcement_id'])
            or row['pdf_path'].lower()!=('finalpage/'+day+'/'+row['announcement_id']+'.PDF').lower()):
        raise ValueError('original implementation PDF path changed')
    return row


def saved_listings(previous,previous_request_sha):
    cached={}
    for folder in sorted((previous/'queries').iterdir()):
        identity=json.loads((folder/'request.json').read_text())
        reserved=json.loads((folder/'reserved-1.json').read_text())
        response=json.loads((folder/'response-1.json').read_text())
        if (folder.name!=digest(identity) or reserved['identity_sha256']!=folder.name
                or reserved['attempt']!=1 or response['identity_sha256']!=folder.name
                or response['reservation_sha256']!=sha256_file(folder/'reserved-1.json')
                or identity['notice_request_sha256']!=previous_request_sha
                or response['status']!='CAPTURED' or digest(response['payload'])!=response['payload_sha256']):
            raise ValueError('previous HTTP identity/response chain changed')
        if identity['payload'] is None:continue
        payload=response['payload']
        if payload['fields']!=['http_response'] or len(payload['rows'])!=1:
            raise ValueError('saved HTTP response envelope changed')
        wire=payload['rows'][0]
        if (wire['status']!=200 or wire['final_url']!=identity['url'] or wire['body_complete'] is not True
                or wire['body_truncated'] is not False or wire['read_error_type'] is not None):
            raise ValueError('saved list response incomplete')
        body=base64.b64decode(wire['body_base64'],validate=True)
        if len(body)>10485760:raise ValueError('saved listing body too large')
        key=digest({'url':identity['url'],'payload':identity['payload']})
        if key in cached:raise ValueError('duplicate original listing response')
        cached[key]=json.loads(body)
    return cached


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);request=Path(a.request)
    if sha256_file(request)!=a.expected_request_sha256:raise ValueError('continuation request changed')
    r=json.loads(request.read_text())
    if (r['status']!='FROZEN_LOW_BETA60_TWO_PDF_CONTINUATION_FROM_SAVED_LISTINGS'
            or set(r['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(repo/f)!=h for f,h in r['method_code_sha256'].items())
            or r['maximum_new_PDF_reservations']!=2 or r['maximum_combined_HTTP_reservations']!=15):
        raise ValueError('continuation method/budget changed')
    if (r['protocol_file']!='docs/research/low-beta60-corporate-continuation-plan-2026-10-21.md'
            or sha256_file(repo/r['protocol_file'])!=r['protocol_sha256']):raise ValueError('protocol changed')
    previous=base/'low-beta60-corporate-sources-20261021';oldpath=previous/'manifest.json'
    if sha256_file(oldpath)!=r['previous_capture_manifest_sha256']:raise ValueError('previous terminal capture changed')
    old=json.loads(oldpath.read_text());prior_request=json.loads((previous/'request.json').read_text())
    if (sha256_file(previous/'request.json')!=r['previous_request_sha256']
            or old['request_sha256']!=r['previous_request_sha256']
            or len(old['documents'])!=8 or len(old['errors'])!=2 or old['pending_cases']
            or old['HTTP_query_reservations']!=8
            or len(list(previous.rglob('reserved-*.json')))!=8
            or set(old['errors'])!=set(r['case_ids'])):raise ValueError('original failure scope changed')
    for f,h in old['artifact_sha256'].items():
        if Path(f).is_absolute() or '..' in Path(f).parts or sha256_file(previous/f)!=h:
            raise ValueError('original captured artifact changed')
    cached=saved_listings(previous,r['previous_request_sha256'])
    def fetch_cached(url,payload):
        key=digest({'url':url,'payload':payload})
        if key not in cached:raise ValueError('unrecorded API page; network fallback forbidden')
        return json.loads(json.dumps(cached[key]))
    cases={c['case_id']:c for c in prior_request['cases']};selected={}
    for key in r['case_ids']:
        case=cases[key]
        rows=query(case['organization_id'],case['instrument'][2:],'',case['publication_day'],
            case['publication_day'],max_pages=2,fetch=fetch_cached)
        row=select_implementation_notice(rows,case)
        if row!=r['selected_original_rows'][key]:raise ValueError('saved original selection changed')
        selected[key]=row
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        write_packet_once(out/'request.json',r)
        if not (out/'progress.json').exists():atomic_json(out/'progress.json',{});atomic_json(out/'errors.json',{})
        docs=json.loads((out/'progress.json').read_text());errors=json.loads((out/'errors.json').read_text())
        if set(docs)&set(errors) or not (set(docs)|set(errors))<=set(cases):raise ValueError('continuation checkpoint scope changed')
        for key,doc in docs.items():
            if sha256_file(out/doc['file'])!=doc['sha256']:raise ValueError('continued PDF checkpoint changed')
        for key,h in errors.items():
            if sha256_file(out/('error-'+key.replace('|','-')+'.json'))!=h:raise ValueError('continued error changed')
        for key,doc in old['documents'].items():
            if key in docs:continue
            target=out/doc['file']
            if target.exists():raise ValueError('uncheckpointed PDF preserved')
            target.write_bytes((previous/doc['file']).read_bytes())
            docs[key]={**doc,'capture_route':'BYTE_IDENTICAL_PRIOR_CAPTURE_REUSE',
                'previous_capture_manifest_sha256':r['previous_capture_manifest_sha256']}
            atomic_json(out/'progress.json',docs)
        journal=QueryJournal(out,max_queries=2,max_attempts=1);next_request=0.
        for key,row in selected.items():
            if key in docs or key in errors:continue
            path=out/(cases[key]['instrument']+'-'+row['day']+'.pdf')
            if path.exists():raise ValueError('uncheckpointed continued PDF preserved')
            url='https://static.cninfo.com.cn/'+row['pdf_path']
            def fetch():
                nonlocal next_request
                pause=next_request-time.monotonic()
                if pause>0:time.sleep(pause)
                try:return read_wire(url,None)
                finally:next_request=time.monotonic()+.3
            try:
                data,receipt=journaled_bytes(journal,{'source':'CNINFO_HTTP','url':url,'payload':None,
                    'notice_request_sha256':a.expected_request_sha256},fetch)
                path.write_bytes(data)
                if not data.startswith(b'%PDF'):raise ValueError('continued response is not PDF')
            except Exception as exc:
                error=out/('error-'+key.replace('|','-')+'.json')
                write_packet_once(error,{'case_id':key,'error_type':type(exc).__name__,'error':str(exc),
                    'HTTP_responses_retained':True});errors[key]=sha256_file(error);atomic_json(out/'errors.json',errors)
            else:
                docs[key]={**row,'instrument':cases[key]['instrument'],'url':url,'file':path.name,
                    'sha256':sha256_file(path),'HTTP_pdf_receipt':receipt,
                    'capture_route':'SAVED_LISTING_NEW_PDF_CONTINUATION',
                    'listing_capture_manifest_sha256':r['previous_capture_manifest_sha256']}
                atomic_json(out/'progress.json',docs)
        count=len(list(out.rglob('reserved-*.json')))
        if count>2 or count+8>15:raise ValueError('combined original HTTP budget exceeded')
        manifest={'status':'LOW_BETA60_CORPORATE_CONTINUATION_CAPTURED_REVIEW_SEPARATE',
            'request_sha256':a.expected_request_sha256,'previous_capture_manifest_sha256':r['previous_capture_manifest_sha256'],
            'documents':docs,'errors':errors,'pending_cases':[k for k in cases if k not in docs and k not in errors],
            'new_API_requests':0,'new_PDF_query_reservations':count,'combined_HTTP_query_reservations':8+count,
            'maximum_combined_HTTP_query_reservations':15,'original_two_parser_errors_preserved':True,
            'artifact_sha256':{str(f.relative_to(out)):sha256_file(f) for f in sorted(out.rglob('*'))
                if f.is_file() and f.name not in ('manifest.json','capture.lock')},
            'documents_financially_reviewed':False,'raw_source_admitted_for_account_replay':False,
            'investment_rule_changed':False,'portfolio_returns_computed':False,'new_2026_queries':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest);print('continued primary capture',len(docs),'/10','errors',len(errors),'combined HTTP',8+count,flush=True)
        return 0 if len(docs)==10 else 2
    finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
