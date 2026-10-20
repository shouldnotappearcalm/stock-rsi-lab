"""Four-identity primary-source continuation; never tax approval or ROI."""
import argparse,fcntl,json,re,time
from pathlib import Path
from scripts.audit_cninfo_report_admission import CNINFO,query
from scripts.capture_budgeted_corporate_notices_pre2026 import read_wire,journaled_bytes,MAX_BODY
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

DAY='2025-04-26';CODE='600580';ORG='gssh0600580'
METHOD_FILES=('scripts/capture_budgeted_wolong_tax_source_pre2026.py',
 'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/audit_cninfo_report_admission.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py')


def select_source(rows,kind):
    patterns={'proposal':r'2024年度利润分配.*(?:资本公积.*转增股本|转增股本).*公告$',
              'annual':r'2024年年度报告(?:（全文）|\(全文\)|全文)?$'}
    if kind not in patterns:raise ValueError('unregistered original source role')
    matches=[r for r in rows if r['code']==CODE and r['day']==DAY
       and not re.search('更正|修订|取消|补充|摘要',r['title']) and re.search(patterns[kind],r['title'])]
    if len(matches)!=1:raise ValueError('unique exact-day original '+kind+' source unavailable')
    row=matches[0]
    if not re.fullmatch('[0-9]+',row['announcement_id']) or row['pdf_path'].lower()!=('finalpage/'+DAY+'/'+row['announcement_id']+'.PDF').lower():
        raise ValueError('primary document ID/path does not match exact date')
    return row


def capture_sources(request,out,request_sha):
    journal=QueryJournal(out,max_queries=request['maximum_http_queries'],max_attempts=1)
    next_request=0.;pdf_urls=set()
    def fetch_bytes(url,payload=None):
        if payload is None:
            if url not in pdf_urls:raise ValueError('PDF not registered by unique primary selection')
        elif (url!=CNINFO+'/new/hisAnnouncement/query' or payload['stock']!=CODE+','+ORG
                or payload['seDate']!=DAY+'~'+DAY or payload['pageNum'] not in ('1','2')
                or payload['pageSize']!='30' or payload['category']!=''):
            raise ValueError('query outside fixed security/exact-day scope')
        def wire():
            nonlocal next_request
            pause=next_request-time.monotonic()
            if pause>0:time.sleep(pause)
            try:return read_wire(url,payload)
            finally:next_request=time.monotonic()+request['minimum_interval_seconds']
        return journaled_bytes(journal,{'source':'CNINFO_HTTP','url':url,'payload':payload,
            'wolong_source_request_sha256':request_sha},wire)
    docs={};errors={}
    try:
        rows=query(ORG,CODE,'',DAY,DAY,max_pages=request['max_pages'],fetch=lambda u,p:json.loads(fetch_bytes(u,dict(p))[0]))
    except Exception as exc:
        errors['query']={'error_type':type(exc).__name__,'error':str(exc)}
        return docs,errors
    for kind in ('proposal','annual'):
        try:
            row=select_source(rows,kind);url='https://static.cninfo.com.cn/'+row['pdf_path'];pdf_urls.add(url)
            data,receipt=fetch_bytes(url);path=out/('SH600580-'+DAY+'-'+kind+'.pdf')
            if path.exists():
                if path.read_bytes()!=data:raise ValueError('previous original PDF bytes differ')
            else:path.write_bytes(data)
            if not data.startswith(b'%PDF'):raise ValueError('original response is not PDF')
        except Exception as exc:
            errors[kind]={'error_type':type(exc).__name__,'error':str(exc)}
        else:docs[kind]={**row,'instrument':'SH600580','url':url,'file':path.name,'sha256':sha256_file(path),'HTTP_pdf_receipt':receipt}
    return docs,errors


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);requestfile=Path(a.request);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir)
 if sha256_file(requestfile)!=a.expected_request_sha256:raise ValueError('source request changed')
 r=json.loads(requestfile.read_text())
 if (r['status']!='FROZEN_WOLONG_CAPITAL_TAX_PRIMARY_SOURCES_PRE2026' or r['day']!=DAY or r['code']!=CODE or r['organization_id']!=ORG
     or r['roles']!=['proposal','annual'] or r['max_pages']!=2 or r['maximum_http_queries']!=4
     or r['max_attempts_per_identity']!=1 or r['minimum_interval_seconds']!=.3 or r['maximum_response_body_bytes']!=MAX_BODY
     or set(r['method_code_sha256'])!=set(METHOD_FILES) or any(sha256_file(repo/f)!=h for f,h in r['method_code_sha256'].items())):
  raise ValueError('frozen exact scope or capture method changed')
 for n,h in r['local_source_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or sha256_file(base/n)!=h:raise ValueError('frozen local source changed')
 for n,h in r['public_evidence_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or sha256_file(repo/n)!=h:raise ValueError('frozen public evidence changed')
 packet=json.loads((base/'budgeted-residual-raw-dev-20261021/codes/SH600580.json').read_text())
 original=[x for x in packet['distributions'] if x['dividOperateDate']=='2025-06-27']
 orgs=json.loads((base/'cninfo-csi500-reports-20261017/plan.json').read_text())['org_by_code']
 if len(original)!=1 or original[0]!=r['original_distribution'] or original[0]['dividPlanAnnounceDate']!=DAY or orgs['SH600580']!=ORG:
  raise ValueError('original distribution date/security/address binding changed')
 out.mkdir(parents=True,exist_ok=True);lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  if (out/'request.json').exists():
   if (out/'request.json').read_bytes()!=requestfile.read_bytes():raise ValueError('source checkpoint request differs')
  else:(out/'request.json').write_bytes(requestfile.read_bytes())
  if (out/'manifest.json').exists():
   m=json.loads((out/'manifest.json').read_text())
   if m['request_sha256']!=a.expected_request_sha256:raise ValueError('source terminal receipt differs')
   for f,h in m['artifact_sha256'].items():
    if sha256_file(out/f)!=h:raise ValueError('source terminal artifact changed')
   print('original terminal capture preserved; no new source calls',flush=True)
   return 0 if not m['errors'] else 2
  docs,errors=capture_sources(r,out,a.expected_request_sha256)
  write_packet_once(out/'documents.json',docs);write_packet_once(out/'errors.json',errors)
  m={'status':'WOLONG_PRIMARY_CONTINUATION_CAPTURE_FINISHED_REVIEW_SEPARATE','request_sha256':a.expected_request_sha256,
    'documents':docs,'errors':errors,'HTTP_query_reservations':len(list(out.rglob('reserved-*.json'))),
    'maximum_HTTP_query_reservations':4,'artifact_sha256':{str(f.relative_to(out)):sha256_file(f) for f in sorted(out.rglob('*')) if f.is_file() and f.name not in ('capture.lock','manifest.json')},
    'financial_review_completed':False,'capital_tax_exemption_granted':False,'original_source_or_investment_rule_modified':False,
    'new_2026_queries':False,'portfolio_returns_computed':False,'objective_achieved':False}
  atomic_json(out/'manifest.json',m);print('Wolong primary sources',len(docs),'/2; errors',list(errors),flush=True)
  return 0 if len(docs)==2 else 2
 finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
