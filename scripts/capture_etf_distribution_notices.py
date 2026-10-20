"""Five preregistered original cash notices; reuses the bounded HTTP journal."""
import argparse,fcntl,json
from pathlib import Path
from scripts.capture_etf_action_sources import capture_sources,MAX_BODY
from scripts.fundamental_query_journal import file_sha

CASES=(
 ('SH510300','2023-01-09','2023-01-16','0ED5'),
 ('SH510300','2024-01-11','2024-01-18','QQFV'),
 ('SH510300','2025-06-11','2025-06-18','ZAU4'),
 ('SH510500','2024-05-10','2024-05-17','LM77'),
 ('SH510500','2025-01-09','2025-01-16','GIJW'))
SOURCES=tuple({'id':code+'-'+ex,'url':'https://www.sse.com.cn/disclosure/fund/announcement/c/new/'+day+'/'+code[2:]+'_'+day.replace('-','')+'_'+suffix+'.pdf',
 'kind':'rule_pdf','role':'cash_distribution_notice','file':code+'-'+ex+'.pdf','publication_day':day}
 for code,day,ex,suffix in CASES)
METHOD_FILES=('scripts/capture_etf_distribution_notices.py','scripts/capture_etf_action_sources.py',
 'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/fundamental_query_journal.py')

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);r=json.loads(Path(a.request).read_text())
 if (file_sha(a.request)!=a.expected_request_sha256 or r['sources']!=list(SOURCES)
  or r['maximum_http_queries']!=5 or r['max_attempts_per_identity']!=1 or r['minimum_interval_seconds']!=.3
  or r['maximum_body_bytes']!=MAX_BODY or set(r['method_code_sha256'])!=set(METHOD_FILES)
  or any(file_sha(repo/n)!=h for n,h in r['method_code_sha256'].items())):raise ValueError('notice capture scope/method changed')
 for n,h in r['local_source_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(base/n)!=h:raise ValueError('source identity changed')
 out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True);lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  path=out/'request.json'
  if path.exists() and path.read_bytes()!=Path(a.request).read_bytes():raise ValueError('request checkpoint changed')
  if not path.exists():path.write_bytes(Path(a.request).read_bytes())
  m=capture_sources(out,r['sources'],a.expected_request_sha256)
  print('Original ETF distribution PDFs',m['captured_documents'],'/5; errors',list(m['errors']),flush=True)
  return 0 if m['captured_documents']==5 and not m['errors'] else 2
 finally:lock.close()

if __name__=='__main__':raise SystemExit(main())
