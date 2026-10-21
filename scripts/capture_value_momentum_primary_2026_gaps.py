"""Seven exact original PDFs; preserve HTTP bytes, no economic admission or returns."""
import argparse,json,re,time
from pathlib import Path
from scripts.capture_budgeted_corporate_notices_pre2026 import journaled_bytes,read_wire
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.fundamental_query_journal import QueryJournal
METHODS=('scripts/capture_value_momentum_primary_2026_gaps.py','scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py','scripts/audit_cninfo_report_admission.py')
def main():
 p=argparse.ArgumentParser()
 for n in ('request','expected-request-sha256','output-dir'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args();repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
 if out.exists() or sha256_file(a.request)!=a.expected_request_sha256:raise ValueError('unused output and frozen request required')
 r=json.loads(Path(a.request).read_bytes());docs=r['documents']
 if (r['maximum_http_queries']!=7 or r['max_attempts']!=1 or len(docs)!=7 or len({d['instrument'] for d in docs})!=7 or set(r['method_code_sha256'])!=set(METHODS)):raise ValueError('seven exact documents required')
 for f,h in r['method_code_sha256'].items():
  if sha256_file(repo/f)!=h:raise ValueError('capture method changed')
 for d in docs:
  if not re.fullmatch('SZ[0-9]{6}',d['instrument']) or not re.fullmatch(r'https://static\.cninfo\.com\.cn/finalpage/'+d['publication_day']+r'/[0-9]+\.PDF',d['url']) or not '2026-10-01'<=d['publication_day']<='2026-10-20':raise ValueError('canonical original identity required')
 if a.preflight_only:print('seven exact original PDFs authenticated; no HTTP');return
 out.mkdir(parents=True);(out/'request.json').write_bytes(Path(a.request).read_bytes());journal=QueryJournal(out,max_queries=7,max_attempts=1);results={};errors={};consecutive=0
 for d in docs:
  c=d['instrument']
  try:
   data,receipt=journaled_bytes(journal,{'source':'CNINFO_HTTP','url':d['url'],'payload':None,'request_sha256':a.expected_request_sha256},lambda:read_wire(d['url'],None))
   if not data.startswith(b'%PDF'):raise ValueError('original PDF bytes required')
   f=out/(c+'.pdf');f.write_bytes(data);results[c]={**d,'file':f.name,'sha256':sha256_file(f),'pdf_receipt':receipt};consecutive=0
  except Exception as e:
   errors[c]={'error_type':type(e).__name__,'error':str(e)};consecutive+=1
  finally:
   atomic_json(out/'progress.json',results);atomic_json(out/'errors.json',errors)
  print(c,'CAPTURED' if c in results else 'ERROR',flush=True)
  if consecutive>=3:break
  time.sleep(.3)
 manifest={'request_sha256':a.expected_request_sha256,'documents':results,'errors':errors,'pending':[d['instrument'] for d in docs if d['instrument'] not in results and d['instrument'] not in errors],'http_query_reservations':len(list(out.rglob('reserved-*.json'))),'capture_complete':len(results)==7,'documents_financially_reviewed':False,'historical_arrival_verified':False,'portfolio_returns_computed':False,'source_admission':False}
 atomic_json(out/'manifest.json',manifest)
 return 0 if manifest['capture_complete'] else 2
if __name__=='__main__':raise SystemExit(main())
