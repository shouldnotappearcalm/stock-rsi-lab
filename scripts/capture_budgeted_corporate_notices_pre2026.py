"""Bounded original implementation notices; no financial approval or ROI."""
import argparse
import base64
import fcntl
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,HTTPRedirectHandler,build_opener

from scripts.audit_cninfo_report_admission import CNINFO,query
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

MAX_BODY=10*1024*1024
METHOD_FILES=('scripts/capture_budgeted_corporate_notices_pre2026.py',
    'scripts/audit_cninfo_report_admission.py','scripts/capture_cninfo_csi500_reports_pre2026.py',
    'scripts/fundamental_query_journal.py')


def journaled_bytes(journal,identity,fetch):
    payload,receipt=journal.query(identity,fetch)
    if payload['fields']!=['http_response'] or len(payload['rows'])!=1:
        raise ValueError('HTTP response envelope changed')
    r=payload['rows'][0]
    if (r['status']!=200 or r['body_truncated'] is not False or r['body_complete'] is not True
            or r['read_error_type'] is not None
            or 'url' in identity and r['final_url']!=identity['url']):
        raise ValueError('HTTP response incomplete or unsuccessful')
    data=base64.b64decode(r['body_base64'],validate=True)
    if len(data)>MAX_BODY:raise ValueError('HTTP response body exceeds bound')
    return data,receipt


def select_notice(rows,case):
    day=case['publication_day'];code=case['instrument'][2:]
    if not '2024-01-01'<=day<='2025-12-31':raise ValueError('primary notice outside development cutoff')
    matches=[r for r in rows if r['code']==code and r['day']==day
        and re.search('权益分派实施(?:的)?公告',r['title'])]
    if len(matches)!=1:raise ValueError('exact implementation notice is not unique')
    row=matches[0];expected='finalpage/'+day+'/'+row['announcement_id']+'.PDF'
    if not re.fullmatch('[0-9]+',row['announcement_id']) or row['pdf_path'].lower()!=expected.lower():
        raise ValueError('original PDF identity/path changed')
    return row


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None


def read_wire(url,payload):
    if payload is not None:
        if url!=CNINFO+'/new/hisAnnouncement/query':raise ValueError('unregistered primary API URL')
    elif not re.fullmatch(r'https://static\.cninfo\.com\.cn/finalpage/20[0-9]{2}-[0-9]{2}-[0-9]{2}/[0-9]+\.PDF',url,re.I):
        raise ValueError('unregistered original PDF URL')
    body=urlencode(payload).encode() if payload is not None else None
    request=Request(url,data=body,headers={'User-Agent':'Mozilla/5.0','Referer':CNINFO+'/'})
    try:response=build_opener(NoRedirect()).open(request,timeout=20)
    except HTTPError as exc:response=exc
    chunks=[];remaining=MAX_BODY+1;error_type=error=None
    try:
        with response:
            while remaining:
                chunk=response.read(min(65536,remaining))
                if not chunk:break
                if not isinstance(chunk,bytes):raise TypeError('HTTP byte stream required')
                chunks.append(chunk[:remaining]);remaining-=len(chunk[:remaining])
    except Exception as exc:
        partial=getattr(exc,'partial',b'')
        if isinstance(partial,bytes):chunks.append(partial[:remaining])
        error_type,error=type(exc).__name__,str(exc)
    data=b''.join(chunks);length=response.headers.get('Content-Length')
    if error_type is None and length is not None:
        try:expected=int(length)
        except ValueError:expected=-1
        if expected<0 or len(data)!=expected:
            error_type,error='ContentLengthMismatch','received byte length differs from response header'
    record={'status':response.code,'content_type':response.headers.get('Content-Type',''),
        'final_url':response.geturl(),'body_base64':base64.b64encode(data).decode(),
        'body_truncated':len(data)>MAX_BODY,'body_complete':error_type is None and len(data)<=MAX_BODY,
        'read_error_type':error_type,'read_error':error}
    return ['http_response'],[record]


def main(argv=None):
    parser=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','source-root','output-dir'):parser.add_argument('--'+n,required=True)
    args=parser.parse_args(argv);requestfile=Path(args.request);repo=Path(__file__).resolve().parents[1]
    if sha256_file(requestfile)!=args.expected_request_sha256:raise ValueError('notice request changed')
    r=json.loads(requestfile.read_text());source=Path(args.source_root)
    if (r['status']!='FROZEN_THIRTEEN_PRE2026_BUDGETED_NONCASH_NOTICES'
            or set(r['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(repo/n)!=h for n,h in r['method_code_sha256'].items())
            or r['max_pages_per_exact_day']!=2 or r['max_attempts_per_identity']!=1
            or r['maximum_consecutive_failed_fresh_cases']!=3 or r['minimum_interval_seconds']!=.3):
        raise ValueError('notice capture method/budget changed')
    for f,key in (('budgeted-residual-raw-dev-20261021/manifest.json','raw_manifest_sha256'),
            ('budgeted-residual-raw-source-audit-20261021.json','raw_audit_sha256'),
            ('cninfo-csi500-reports-20261017/plan.json','org_map_plan_sha256')):
        if sha256_file(source/f)!=r[key]:raise ValueError('notice source identity changed')
    audit=json.loads((source/'budgeted-residual-raw-source-audit-20261021.json').read_text())
    expected={x['instrument']+'|'+x['record']['dividOperateDate']:x for x in audit['noncash_distributions_requiring_review']}
    orgs=json.loads((source/'cninfo-csi500-reports-20261017/plan.json').read_text())['org_by_code']
    cases=r['cases'];ids=[c['case_id'] for c in cases]
    if len(cases)!=13 or len(set(ids))!=13 or set(ids)!=set(expected):raise ValueError('complete13event scope required')
    for c in cases:
        original=expected[c['case_id']]
        if (c['instrument']!=original['instrument'] or c['record']!=original['record']
                or c['publication_day']!=original['record']['dividPlanDate']
                or c['organization_id']!=orgs[c['instrument']]):raise ValueError('case source changed')
    reused=r['reuse_documents'];fresh=[c for c in cases if c['case_id'] not in reused]
    if len(reused)!=1 or set(reused)-set(ids) or r['maximum_http_query_reservations']!=len(fresh)*3:
        raise ValueError('registered HTTP scope changed')
    for key,v in reused.items():
        directory=source/v['directory']
        if (Path(v['directory']).name!=v['directory'] or Path(v['file']).name!=v['file']
                or sha256_file(directory/'reviewed-manifest.json')!=v['reviewed_manifest_sha256']
                or sha256_file(directory/v['file'])!=v['sha256']):raise ValueError('reused primary proof changed')
        proof=json.loads((directory/'reviewed-manifest.json').read_text())
        if v['metadata'] not in proof['documents']:raise ValueError('reused document absent from original review')
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        if (out/'request.json').exists():
            if (out/'request.json').read_bytes()!=requestfile.read_bytes():raise ValueError('notice checkpoint request changed')
        else:
            (out/'request.json').write_bytes(requestfile.read_bytes());atomic_json(out/'progress.json',{});atomic_json(out/'errors.json',{})
        docs=json.loads((out/'progress.json').read_text());errors=json.loads((out/'errors.json').read_text())
        if set(docs)&set(errors) or not (set(docs)|set(errors))<=set(ids):raise ValueError('checkpoint case set changed')
        for k,d in docs.items():
            if sha256_file(out/d['file'])!=d['sha256']:raise ValueError('primary checkpoint bytes changed')
        for k,h in errors.items():
            if sha256_file(out/('error-'+k.replace('|','-')+'.json'))!=h:raise ValueError('primary error changed')
        if (out/'stopped.json').exists():raise ValueError('previous source stop preserved')
        for key,v in reused.items():
            if key in docs:continue
            data=(source/v['directory']/v['file']).read_bytes()
            if not data.startswith(b'%PDF'):raise ValueError('reused primary is not PDF')
            path=out/v['file']
            if path.exists():raise ValueError('uncheckpointed original PDF preserved')
            path.write_bytes(data);docs[key]={**v['metadata'],'capture_route':'BYTE_IDENTICAL_REVIEWED_PRIMARY_REUSE',
                'original_reviewed_manifest_sha256':v['reviewed_manifest_sha256']};atomic_json(out/'progress.json',docs)
        journal=QueryJournal(out,max_queries=r['maximum_http_query_reservations'],max_attempts=1);next_request=0.
        def fetch_bytes(url,payload=None):
            def wire():
                nonlocal next_request
                pause=next_request-time.monotonic()
                if pause>0:time.sleep(pause)
                try:return read_wire(url,payload)
                finally:next_request=time.monotonic()+r['minimum_interval_seconds']
            return journaled_bytes(journal,{'source':'CNINFO_HTTP','url':url,'payload':payload,
                'notice_request_sha256':args.expected_request_sha256},wire)
        def fetch_json(url,payload):
            data,_=fetch_bytes(url,dict(payload));return json.loads(data)
        consecutive=0
        for c in fresh:
            key=c['case_id']
            if key in docs:consecutive=0;continue
            if key in errors:consecutive+=1
            else:
                code,day=c['instrument'],c['publication_day']
                try:
                    rows=query(c['organization_id'],code[2:],'',day,day,max_pages=2,fetch=fetch_json)
                    row=select_notice(rows,c);url='https://static.cninfo.com.cn/'+row['pdf_path']
                    data,receipt=fetch_bytes(url)
                    path=out/(code+'-'+day+'.pdf')
                    if path.exists():raise ValueError('uncheckpointed primary response preserved')
                    path.write_bytes(data)
                    if not data.startswith(b'%PDF'):raise ValueError('original response is not a PDF')
                except Exception as exc:
                    error=out/('error-'+key.replace('|','-')+'.json')
                    write_packet_once(error,{'case_id':key,'error_type':type(exc).__name__,'error':str(exc),
                        'HTTP_responses_retained':True,'financial_approval_granted':False})
                    errors[key]=sha256_file(error);atomic_json(out/'errors.json',errors);consecutive+=1
                    print('primary source error retained',key,type(exc).__name__,flush=True)
                else:
                    docs[key]={**row,'instrument':code,'url':url,'file':path.name,'sha256':sha256_file(path),
                        'HTTP_pdf_receipt':receipt,'capture_route':'JOURNALED_ORIGINAL_PRIMARY_HTTP'}
                    atomic_json(out/'progress.json',docs);consecutive=0
                    print('primary captured',key,path.name,flush=True)
            if consecutive>=3:
                write_packet_once(out/'stopped.json',{'reason':'THREE_CONSECUTIVE_FAILED_FRESH_CASES','last_case_id':key});break
        artifact_hashes={str(p.relative_to(out)):sha256_file(p) for p in sorted(out.rglob('*'))
            if p.is_file() and p.name not in ('manifest.json','capture.lock')}
        manifest={'status':'BUDGETED_RESIDUAL_NONCASH_PRIMARY_CAPTURE_COMPLETE_REVIEW_SEPARATE',
            'request_sha256':args.expected_request_sha256,'raw_manifest_sha256':r['raw_manifest_sha256'],
            'raw_audit_sha256':r['raw_audit_sha256'],'documents':docs,'errors':errors,
            'pending_cases':[k for k in ids if k not in docs and k not in errors],
            'HTTP_query_reservations':len(list(out.rglob('reserved-*.json'))),
            'maximum_HTTP_query_reservations':r['maximum_http_query_reservations'],'artifact_sha256':artifact_hashes,
            'documents_financially_reviewed':False,'raw_source_admitted_for_account_replay':False,
            'investment_rule_changed':False,'portfolio_returns_computed':False,'new_2026_queries':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
        print('primary capture complete',len(docs),'/13; errors',len(errors),flush=True)
        return 0 if len(docs)==13 else 2
    finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
