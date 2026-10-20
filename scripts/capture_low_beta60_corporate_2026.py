"""Fixed primary-source capture only; no investment decisions or event admission."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from scripts.audit_cninfo_report_admission import CNINFO,publication_date
from scripts.capture_budgeted_corporate_notices_pre2026 import journaled_bytes,read_wire
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.fundamental_query_journal import QueryJournal

METHOD_FILES=('scripts/capture_low_beta60_corporate_2026.py',
 'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/audit_cninfo_report_admission.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py')
PDF=re.compile(r'https://static\.cninfo\.com\.cn/finalpage/(2026-\d{2}-\d{2})/[0-9]+\.PDF')


def select_original(data,case):
    if not isinstance(data,dict) or type(data.get('totalAnnouncement')) is not int:
        raise ValueError('typed complete listing required')
    rows=data.get('announcements') or []
    if (data['totalAnnouncement']>30 or data['totalAnnouncement']!=len(rows)
            or not all(isinstance(r,dict) for r in rows)):
        raise ValueError('single complete announcement page required')
    matches=[]
    for row in rows:
        title=row['announcementTitle']
        if (row['secCode']!=case['instrument'][2:]
                or type(row['announcementTime']) is not int
                or publication_date(row['announcementTime'])!=case['publication_day']):
            raise ValueError('listing contains another security or publication date')
        if not isinstance(title,str):raise ValueError('text announcement title required')
        title=re.sub(r'<[^>]*>','',title)
        if title.split('：')[-1]==case['exact_title']:matches.append(row)
    if len(matches)!=1:raise ValueError('unique exact original implementation title required')
    row=matches[0];identity=row['announcementId']
    if (not isinstance(identity,str) or not re.fullmatch('[0-9]+',identity)
            or row['adjunctUrl']!='finalpage/'+case['publication_day']+'/'+identity+'.PDF'):
        raise ValueError('canonical original announcement path required')
    return 'https://static.cninfo.com.cn/'+row['adjunctUrl'],row


def capture_documents(request,base,out,fetch,*,request_sha):
    base,out=Path(base),Path(out)
    if out.exists():raise ValueError('preserve previous capture; automatic resume forbidden')
    cases=request['documents'];ids=[c['document_id'] for c in cases]
    expected=sum(0 if 'reuse_file' in c else 1 if 'url' in c else 2 for c in cases)
    if (not cases or len(set(ids))!=len(ids) or any(not re.fullmatch('[A-Za-z0-9_-]+',i) for i in ids)
            or type(request['maximum_http_queries']) is not int
            or request['maximum_http_queries']!=expected or expected<=0):
        raise ValueError('exact distinct source scope and bounded integer budget required')
    reused={}
    for c in cases:
        if not re.fullmatch('(SH|SZ)[0-9]{6}',c['instrument']) or not '2026-01-01'<=c['publication_day']<='2026-10-13':
            raise ValueError('explicit fixed 2026 issuer/publication required')
        if 'reuse_file' in c:
            path=Path(c['reuse_file'])
            if path.is_absolute() or '..' in path.parts:raise ValueError('local reused source must stay inside source root')
            data=(base/path).read_bytes()
            if hashlib.sha256(data).hexdigest()!=c['reuse_sha256'] or not data.startswith(b'%PDF'):
                raise ValueError('original reused PDF bytes changed')
            reused[c['document_id']]=data
        elif 'url' in c:
            match=PDF.fullmatch(c['url'])
            if match is None or match[1]!=c['publication_day']:raise ValueError('bound original PDF URL/date required')
        elif not isinstance(c.get('exact_title'),str) or not re.fullmatch('[A-Za-z0-9]+',c.get('organization_id','')):
            raise ValueError('bound exact original listing required')
    out.mkdir(parents=True);atomic_json(out/'request.json',request)
    journal=QueryJournal(out,max_queries=expected,max_attempts=1)
    docs={};errors={};consecutive=0;stopped=False;abnormal=True
    def get(url,payload=None):
        return journaled_bytes(journal,{'source':'CNINFO_HTTP','url':url,'payload':payload,
            'notice_request_sha256':request_sha},lambda:fetch(url,payload))
    try:
        for c in cases:
            key=c['document_id']
            try:
                row=None;receipt=None;listing_receipt=None;url=c.get('url')
                if key in reused:data=reused[key]
                else:
                    if url is None:
                        payload={'pageNum':'1','pageSize':'30','column':'szse','tabName':'fulltext',
                            'plate':'','stock':c['instrument'][2:]+','+c['organization_id'],
                            'searchkey':'','secid':'','category':'','trade':'',
                            'seDate':c['publication_day']+'~'+c['publication_day'],
                            'sortName':'','sortType':'','isHLtitle':'true'}
                        body,listing_receipt=get(CNINFO+'/new/hisAnnouncement/query',payload)
                        url,row=select_original(json.loads(body),c)
                    data,receipt=get(url)
                    if not data.startswith(b'%PDF'):raise ValueError('original HTTP response is not PDF')
                path=out/(key+'.pdf');path.write_bytes(data)
                docs[key]={'instrument':c['instrument'],'publication_day':c['publication_day'],
                    'file':path.name,'sha256':sha256_file(path),'url':url,'listing_row':row,
                    'listing_receipt':listing_receipt,'pdf_receipt':receipt,
                    'capture_route':'BYTE_IDENTICAL_REUSE' if key in reused else 'JOURNALED_ORIGINAL_HTTP'}
                atomic_json(out/'progress.json',docs);consecutive=0
            except Exception as exc:
                errors[key]={'error_type':type(exc).__name__,'error':str(exc)}
                atomic_json(out/'errors.json',errors);consecutive+=1
                if consecutive>=3:stopped=True;break
        abnormal=False
    finally:
        manifest={'status':'PRIMARY_CAPTURE_ONLY_FINANCIAL_REVIEW_SEPARATE','request_sha256':request_sha,
            'documents':docs,'errors':errors,'pending_documents':[i for i in ids if i not in docs and i not in errors],
            'http_query_reservations':len(list(out.rglob('reserved-*.json'))),
            'maximum_http_queries':expected,'stopped_after_three_failures':stopped,'abnormal_termination':abnormal,
            'capture_complete':len(docs)==len(cases) and not abnormal,
            'artifact_sha256':{str(p.relative_to(out)):sha256_file(p) for p in sorted(out.rglob('*'))
                if p.is_file() and p.name!='manifest.json'},
            'documents_financially_reviewed':False,'admitted_for_account_replay':False,
            'historical_arrival_verified':False,'investment_rule_changed':False,
            'portfolio_returns_computed':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
    return manifest


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);path=Path(a.request);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root)
    if sha256_file(path)!=a.expected_request_sha256:raise ValueError('external request SHA changed')
    r=json.loads(path.read_bytes())
    if (r['status']!='FROZEN_LOW_BETA60_2026_SIX_PRIMARY_DOCUMENTS_NO_ROI'
            or r['maximum_http_queries']!=6 or r['minimum_interval_seconds']!=.3
            or r['max_attempts_per_identity']!=1 or set(r['method_code_sha256'])!=set(METHOD_FILES)
            or [c['document_id'] for c in r['documents']]!=[
                'SH601128-20260603','SZ000937-20260611','SH601918-20260130',
                'SZ000975-20260417','SH603826-20260708','SZ000937-20260827']
            or Path(a.output_dir)!=base/'low-beta60-corporate-2026-20261021'):
        raise ValueError('fixed six-document source scope changed')
    for bindings,root in ((r['method_code_sha256'],repo),(r['public_evidence_sha256'],repo),
                          (r['local_source_sha256'],base)):
        for f,h in bindings.items():
            if Path(f).is_absolute() or '..' in Path(f).parts or sha256_file(root/f)!=h:
                raise ValueError('frozen method/source bytes changed')
    next_request=0.
    def fetch(url,payload):
        nonlocal next_request
        pause=next_request-time.monotonic()
        if pause>0:time.sleep(pause)
        try:return read_wire(url,payload)
        finally:next_request=time.monotonic()+.3
    result=capture_documents(r,base,Path(a.output_dir),fetch,request_sha=a.expected_request_sha256)
    print('primary documents',len(result['documents']),'/6; errors',len(result['errors']),flush=True)
    return 0 if result['capture_complete'] else 2


if __name__=='__main__':raise SystemExit(main())
