"""Two registered primary originals and four exact reviewed copies; no ROI."""
import argparse,fcntl,json
from pathlib import Path
from scripts.capture_budgeted_corporate_notices_pre2026 import read_wire,journaled_bytes
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

FRESH=(
 {'instrument':'SZ002508','day':'2024-01-03','url':'https://static.cninfo.com.cn/finalpage/2024-01-03/1218790856.PDF','file':'SZ002508-2024-01-03.pdf'},
 {'instrument':'SZ001389','day':'2024-04-01','url':'https://static.cninfo.com.cn/finalpage/2024-04-01/1219474753.PDF','file':'SZ001389-2024-04-01.pdf'})
REUSE=('SZ002155-2025-06-07.pdf','SZ002837-2024-05-18.pdf','SZ002837-2025-05-23.pdf','SZ002984-2024-04-12.pdf')
METHOD_FILES=('scripts/capture_value_momentum_primary_pre2026.py','scripts/capture_budgeted_corporate_notices_pre2026.py',
 'scripts/audit_cninfo_report_admission.py','scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py')

def validate_scope(r):
 if (r['status']!='FROZEN_VALUE_MOMENTUM_TWO_PRIMARY_ORIGINALS' or r['fresh_documents']!=list(FRESH)
     or type(r['maximum_new_HTTP_reservations']) is not int or r['maximum_new_HTTP_reservations']!=2
     or type(r['max_attempts_per_identity']) is not int or r['max_attempts_per_identity']!=1):
  raise ValueError('only two exact registered pre2026 originals and one attempt each allowed')

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv)
 request=Path(a.request);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root)
 if sha256_file(request)!=a.expected_request_sha256:raise ValueError('primary request changed')
 r=json.loads(request.read_text());validate_scope(r)
 if (set(r['method_code_sha256'])!=set(METHOD_FILES)
     or any(sha256_file(repo/n)!=h for n,h in r['method_code_sha256'].items())):raise ValueError('primary method changed')
 for n,h in r['public_inputs_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or sha256_file(repo/n)!=h:raise ValueError('primary public input changed')
 for n,h in r['local_inputs_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or sha256_file(base/n)!=h:raise ValueError('primary local input changed')
 directory=base/'budgeted-residual-corporate-reviewed-20261021'
 proof=json.loads((directory/'reviewed-manifest.json').read_text())
 if [d['file'] for d in r['reuse_documents']]!=list(REUSE):raise ValueError('four complete noncash source documents required')
 for d in r['reuse_documents']:
  if d not in proof['documents'] or sha256_file(directory/d['file'])!=d['sha256']:raise ValueError('reviewed original changed')
 if a.preflight_only:print('two fixed HTTP originals; four authenticated copies; no output/network',flush=True);return 0
 out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
 lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  if (out/'request.json').exists():
   if (out/'request.json').read_bytes()!=request.read_bytes():raise ValueError('primary checkpoint request changed')
  else:
   (out/'request.json').write_bytes(request.read_bytes());atomic_json(out/'progress.json',{});atomic_json(out/'errors.json',{})
  progress=json.loads((out/'progress.json').read_text());errors=json.loads((out/'errors.json').read_text())
  allowed=set(REUSE)|{d['file'] for d in FRESH}
  if set(progress)&set(errors) or not (set(progress)|set(errors))<=allowed:raise ValueError('primary checkpoint universe changed')
  for name,d in progress.items():
   if sha256_file(out/name)!=d['sha256']:raise ValueError('primary checkpoint bytes changed')
  for name,h in errors.items():
   if sha256_file(out/(name+'.error.json'))!=h:raise ValueError('primary checkpoint error changed')
  for d in r['reuse_documents']:
   name=d['file']
   if name in progress:continue
   if (out/name).exists():raise ValueError('uncheckpointed primary copy preserved')
   data=(directory/name).read_bytes()
   if not data.startswith(b'%PDF'):raise ValueError('original copy is not PDF')
   (out/name).write_bytes(data);progress[name]={**d,'capture_route':'BYTE_IDENTICAL_REVIEWED_PRIMARY_REUSE'};atomic_json(out/'progress.json',progress)
  journal=QueryJournal(out,max_queries=2,max_attempts=1)
  for d in FRESH:
   name=d['file']
   if name in progress or name in errors:continue
   if (out/name).exists():raise ValueError('uncheckpointed primary response preserved')
   try:
    data,receipt=journaled_bytes(journal,{'source':'CNINFO_HTTP','url':d['url'],'payload':None,
       'primary_request_sha256':a.expected_request_sha256},lambda:read_wire(d['url'],None))
    (out/name).write_bytes(data)
    if not data.startswith(b'%PDF'):raise ValueError('original response is not PDF')
   except Exception as exc:
    record=out/(name+'.error.json');write_packet_once(record,{'file':name,'error_type':type(exc).__name__,'error':str(exc),'response_retained':True})
    errors[name]=sha256_file(record);atomic_json(out/'errors.json',errors);print('primary error retained',name,flush=True)
   else:
    progress[name]={**d,'sha256':sha256_file(out/name),'HTTP_pdf_receipt':receipt,'capture_route':'JOURNALED_ORIGINAL_PRIMARY_HTTP'}
    atomic_json(out/'progress.json',progress);print('primary captured',name,flush=True)
  manifest={'status':'VALUE_MOMENTUM_PRIMARY_CAPTURE_REVIEW_SEPARATE','request_sha256':a.expected_request_sha256,
   'documents':progress,'errors':errors,'pending_files':sorted(allowed-set(progress)-set(errors)),
   'HTTP_query_reservations':len(list(out.rglob('reserved-*.json'))),'maximum_HTTP_query_reservations':2,
   'documents_financially_reviewed':False,'listing_boundary_verified':False,'supplementary_distribution_verified':False,
   'raw_source_admitted_for_account_replay':False,'investment_rules_changed':False,'portfolio_returns_computed':False,'new_2026_market_queries':False}
  atomic_json(out/'manifest.json',manifest);return 0 if len(progress)==6 and not errors else 2
 finally:lock.close()

if __name__=='__main__':raise SystemExit(main())
