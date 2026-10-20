"""Bounded post-event/pre2026 primary confirmation; evaluator-only, never signal."""
import argparse,fcntl,json,re,time
from pathlib import Path
from scripts.audit_cninfo_report_admission import CNINFO,query
from scripts.capture_budgeted_corporate_notices_pre2026 import read_wire,journaled_bytes,MAX_BODY
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

START,END='2025-07-01','2025-08-31';CODE,ORG='600580','gssh0600580';CATEGORY='category_bndbg_szsh'
METHOD_FILES=('scripts/capture_budgeted_wolong_halfyear_pre2026.py',
 'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/audit_cninfo_report_admission.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py')


def select_halfyear(rows):
 matches=[r for r in rows if r['code']==CODE and START<=r['day']<=END
   and not re.search('更正|修订|取消|补充|摘要',r['title']) and re.search(r'2025年半年度报告(?:（全文）|\(全文\)|全文)?$',r['title'])]
 if len(matches)!=1:raise ValueError('unique original2025halfyear report in frozen publication window required')
 row=matches[0]
 if not re.fullmatch('[0-9]+',row['announcement_id']) or row['pdf_path'].lower()!=('finalpage/'+row['day']+'/'+row['announcement_id']+'.PDF').lower():
  raise ValueError('original halfyear PDF ID/publication path changed')
 return row


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);requestfile=Path(a.request);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir)
 if sha256_file(requestfile)!=a.expected_request_sha256:raise ValueError('halfyear source request changed')
 r=json.loads(requestfile.read_text())
 if (r['status']!='FROZEN_WOLONG_2025H1_ACTUAL_CAPITAL_SOURCE_PRE2026' or r['window']!=[START,END]
     or r['code']!=CODE or r['organization_id']!=ORG or r['category']!=CATEGORY
     or r['max_pages']!=2 or r['maximum_http_queries']!=3 or r['max_attempts_per_identity']!=1
     or r['minimum_interval_seconds']!=.3 or r['maximum_response_body_bytes']!=MAX_BODY
     or set(r['method_code_sha256'])!=set(METHOD_FILES) or any(sha256_file(repo/f)!=h for f,h in r['method_code_sha256'].items())):
  raise ValueError('halfyear capture method/window/budget changed')
 for n,h in r['local_source_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or sha256_file(base/n)!=h:raise ValueError('original primary source binding changed')
 for n,h in r['public_evidence_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or sha256_file(repo/n)!=h:raise ValueError('public original failure evidence changed')
 packet=json.loads((base/'budgeted-residual-raw-dev-20261021/codes/SH600580.json').read_text())
 original=[x for x in packet['distributions'] if x['dividOperateDate']=='2025-06-27']
 orgs=json.loads((base/'cninfo-csi500-reports-20261017/plan.json').read_text())['org_by_code']
 if len(original)!=1 or original[0]!=r['original_distribution'] or orgs['SH600580']!=ORG:
  raise ValueError('original event or source address changed')
 out.mkdir(parents=True,exist_ok=True);lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  if (out/'request.json').exists():
   if (out/'request.json').read_bytes()!=requestfile.read_bytes():raise ValueError('halfyear source checkpoint request changed')
  else:(out/'request.json').write_bytes(requestfile.read_bytes())
  if (out/'manifest.json').exists():
   m=json.loads((out/'manifest.json').read_text())
   if m['request_sha256']!=a.expected_request_sha256:raise ValueError('terminal halfyear request mismatch')
   for f,h in m['artifact_sha256'].items():
    if sha256_file(out/f)!=h:raise ValueError('terminal halfyear bytes changed')
   print('terminal halfyear capture preserved; no new source calls',flush=True)
   return 0 if not m['errors'] else 2
  journal=QueryJournal(out,max_queries=3,max_attempts=1);next_request=0.;pdf_urls=set()
  def fetch_bytes(url,payload=None):
   if payload is None:
    if url not in pdf_urls:raise ValueError('unregistered halfyear PDF URL')
   elif (url!=CNINFO+'/new/hisAnnouncement/query' or payload['stock']!=CODE+','+ORG or payload['seDate']!=START+'~'+END
         or payload['category']!=CATEGORY or payload['pageNum'] not in ('1','2') or payload['pageSize']!='30'):
    raise ValueError('halfyear query outside frozen scope')
   def wire():
    nonlocal next_request
    pause=next_request-time.monotonic()
    if pause>0:time.sleep(pause)
    try:return read_wire(url,payload)
    finally:next_request=time.monotonic()+.3
   return journaled_bytes(journal,{'source':'CNINFO_HTTP','url':url,'payload':payload,'wolong_halfyear_request_sha256':a.expected_request_sha256},wire)
  docs={};errors={}
  try:
   rows=query(ORG,CODE,CATEGORY,START,END,max_pages=2,fetch=lambda u,p:json.loads(fetch_bytes(u,dict(p))[0]))
   row=select_halfyear(rows);url='https://static.cninfo.com.cn/'+row['pdf_path'];pdf_urls.add(url)
   data,receipt=fetch_bytes(url);path=out/('SH600580-'+row['day']+'-halfyear.pdf')
   if path.exists():
    if path.read_bytes()!=data:raise ValueError('original halfyear bytes differ')
   else:path.write_bytes(data)
   if not data.startswith(b'%PDF'):raise ValueError('original halfyear response is notPDF')
   docs['halfyear']={**row,'instrument':'SH600580','url':url,'file':path.name,'sha256':sha256_file(path),'HTTP_pdf_receipt':receipt}
  except Exception as exc:errors['halfyear']={'error_type':type(exc).__name__,'error':str(exc)}
  write_packet_once(out/'documents.json',docs);write_packet_once(out/'errors.json',errors)
  m={'status':'WOLONG_HALF_YEAR_PRIMARY_CAPTURE_FINISHED_REVIEW_SEPARATE','request_sha256':a.expected_request_sha256,
   'documents':docs,'errors':errors,'HTTP_query_reservations':len(list(out.rglob('reserved-*.json'))),'maximum_HTTP_query_reservations':3,
   'artifact_sha256':{str(f.relative_to(out)):sha256_file(f) for f in sorted(out.rglob('*')) if f.is_file() and f.name not in ('manifest.json','capture.lock')},
   'source_role':'POST_EVENT_ACTUAL_CAPITAL_MOVEMENT_CONFIRMATION_EVALUATOR_ONLY_NOT_DECISION_RECORD',
   'historical_arrival_certified':False,'financial_review_completed':False,'capital_tax_exemption_granted':False,
   'original_source_or_investment_rule_modified':False,'new_2026_queries':False,'portfolio_returns_computed':False,'objective_achieved':False}
  atomic_json(out/'manifest.json',m);print('halfyear source captured',len(docs),'errors',list(errors),flush=True)
  return 0 if len(docs)==1 else 2
 finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
