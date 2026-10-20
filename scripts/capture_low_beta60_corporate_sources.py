"""Bounded low-beta60 primary questions; no inferred income or portfolio ROI."""
import argparse
import fcntl
import json
import time
from pathlib import Path
from datetime import date
from scripts.audit_cninfo_report_admission import CNINFO,query
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.fundamental_query_journal import QueryJournal,write_packet_once
from scripts.capture_budgeted_corporate_notices_pre2026 import journaled_bytes,select_notice,read_wire

METHOD_FILES=('scripts/capture_low_beta60_corporate_sources.py',
    'scripts/capture_budgeted_corporate_notices_pre2026.py',
    'scripts/audit_cninfo_report_admission.py','scripts/capture_cninfo_csi500_reports_pre2026.py',
    'scripts/fundamental_query_journal.py')

def source_cases(audit,packets):
    result={}
    def add(code,day,kind,record):
        key=code+'|'+day
        if (key in result or not '2024-01-01'<=day<='2025-12-31'
                or date.fromisoformat(day).isoformat()!=day):
            raise ValueError('unique pre2026 source case required')
        result[key]={'case_id':key,'instrument':code,'kind':kind,'source_record':record}
    for item in audit['noncash_distributions_requiring_review']:
        code=item['instrument'];row=item['record']
        if row not in packets[code]['distributions']:raise ValueError('audit distribution differs from source packet')
        add(code,row['dividOperateDate'],'NONCASH',row)
    for code,day in audit['adjustments_without_distribution']:
        matches=[r for r in packets[code]['adjustments'] if r['dividOperateDate']==day]
        if len(matches)!=1 or any(r['dividOperateDate']==day for r in packets[code]['distributions']):
            raise ValueError('audit unmatched adjustment differs from source packet')
        add(code,day,'ADJUSTMENT_WITHOUT_DISTRIBUTION',matches[0])
    return result


def main(argv=None):
    parser=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','source-root','output-dir'):parser.add_argument('--'+n,required=True)
    args=parser.parse_args(argv);requestfile=Path(args.request);repo=Path(__file__).resolve().parents[1]
    if sha256_file(requestfile)!=args.expected_request_sha256:raise ValueError('notice request changed')
    r=json.loads(requestfile.read_text());source=Path(args.source_root)
    if (r['status']!='FROZEN_TEN_LOW_BETA60_PRIMARY_SOURCE_QUESTIONS'
            or set(r['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(repo/n)!=h for n,h in r['method_code_sha256'].items())
            or r['max_pages_per_exact_day']!=2 or r['max_attempts_per_identity']!=1
            or r['maximum_consecutive_failed_fresh_cases']!=3 or r['minimum_interval_seconds']!=.3):
        raise ValueError('notice capture method/budget changed')
    if (r['protocol_file']!='docs/research/low-beta60-corporate-source-plan-2026-10-21.md'
            or sha256_file(repo/r['protocol_file'])!=r['protocol_sha256']):
        raise ValueError('primary source protocol changed')
    for f,key in (('low-beta60-raw-dev-20261021/manifest.json','raw_manifest_sha256'),
            ('low-beta60-raw-source-audit-20261021.json','raw_audit_sha256'),
            ('cninfo-csi500-reports-20261017/plan.json','org_map_plan_sha256')):
        if sha256_file(source/f)!=r[key]:raise ValueError('notice source identity changed')
    audit=json.loads((source/'low-beta60-raw-source-audit-20261021.json').read_text())
    manifest=json.loads((source/'low-beta60-raw-dev-20261021/manifest.json').read_text());packets={}
    for code,h in manifest['per_code_sha256'].items():
        path=source/'low-beta60-raw-dev-20261021/codes'/(code+'.json')
        if sha256_file(path)!=h:raise ValueError('raw source packet changed')
        packets[code]=json.loads(path.read_text())
    expected=source_cases(audit,packets)
    orgs=json.loads((source/'cninfo-csi500-reports-20261017/plan.json').read_text())['org_by_code']
    cases=r['cases'];ids=[c['case_id'] for c in cases]
    if (len(cases)!=10 or len(set(ids))!=10 or set(ids)!=set(expected)
            or sum(c['kind']=='NONCASH' for c in cases)!=4):
        raise ValueError('complete four noncash and six unmatched source questions required')
    for c in cases:
        original=expected[c['case_id']]
        if any(c[k]!=v for k,v in original.items()) or c['organization_id']!=orgs[c['instrument']]:
            raise ValueError('case source changed')
        if c['kind']=='NONCASH':
            if c['publication_day']!=c['source_record']['dividPlanDate']:raise ValueError('noncash publication changed')
        elif c['case_id'] not in r['reuse_documents']:
            related=c['related_vendor_distribution']
            if (related not in packets[c['instrument']]['distributions']
                    or c['publication_day']!=related['dividPlanDate']
                    or not related['dividOperateDate']<c['source_record']['dividOperateDate']):
                raise ValueError('paired announcement query must originate from an actual earlier source row')
    reused=r['reuse_documents'];fresh=[c for c in cases if c['case_id'] not in reused]
    if len(reused)!=5 or set(reused)-set(ids) or r['maximum_http_query_reservations']!=len(fresh)*3:
        raise ValueError('registered HTTP scope changed')
    for key,v in reused.items():
        directory=source/v['directory']
        if (Path(v['directory']).name!=v['directory'] or Path(v['file']).name!=v['file']
                or sha256_file(directory/'reviewed-manifest.json')!=v['reviewed_manifest_sha256']
                or sha256_file(directory/v['file'])!=v['sha256']):raise ValueError('reused primary proof changed')
        proof=json.loads((directory/'reviewed-manifest.json').read_text())
        if v['metadata'] not in proof['documents']:raise ValueError('reused document absent from original review')
        c=next(c for c in cases if c['case_id']==key)
        if v['metadata']['instrument']!=c['instrument'] or v['metadata']['day']!=c['publication_day']:
            raise ValueError('reused original is not the specified issuer announcement')
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
        manifest={'status':'LOW_BETA60_PRIMARY_SOURCE_QUESTIONS_CAPTURED_REVIEW_SEPARATE',
            'request_sha256':args.expected_request_sha256,'raw_manifest_sha256':r['raw_manifest_sha256'],
            'raw_audit_sha256':r['raw_audit_sha256'],'documents':docs,'errors':errors,
            'pending_cases':[k for k in ids if k not in docs and k not in errors],
            'HTTP_query_reservations':len(list(out.rglob('reserved-*.json'))),
            'maximum_HTTP_query_reservations':r['maximum_http_query_reservations'],'artifact_sha256':artifact_hashes,
            'documents_financially_reviewed':False,'raw_source_admitted_for_account_replay':False,
            'investment_rule_changed':False,'portfolio_returns_computed':False,'new_2026_queries':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
        print('primary capture complete',len(docs),'/10; errors',len(errors),flush=True)
        return 0 if len(docs)==10 else 2
    finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
