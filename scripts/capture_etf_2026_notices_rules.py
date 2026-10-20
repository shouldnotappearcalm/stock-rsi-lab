"""Three preregistered cash notices and one effective-2026 rule; reuses the bounded HTTP journal."""
import argparse,fcntl,json
from pathlib import Path
from scripts.capture_etf_action_sources import capture_sources,MAX_BODY
from scripts.fundamental_query_journal import file_sha

SOURCES=(
 {'id':'SH510300-2026-01-19','url':'https://www.sse.com.cn/disclosure/fund/announcement/c/new/2026-01-12/510300_20260112_VTCZ.pdf','kind':'rule_pdf','role':'cash_distribution_notice','file':'SH510300-2026-01-19.pdf','publication_day':'2026-01-12','host_role':'SSE_hosted_manager_original'},
 {'id':'SH510500-2026-01-16','url':'https://www.sse.com.cn/disclosure/fund/announcement/c/new/2026-01-09/510500_20260109_5K7U.pdf','kind':'rule_pdf','role':'cash_distribution_notice','file':'SH510500-2026-01-16.pdf','publication_day':'2026-01-09','host_role':'SSE_hosted_manager_original'},
 {'id':'SH510500-2026-07-15','url':'https://static.howbuy.com/gkxx/ggfile//2026/2026-7/2026-07-08/5355354.pdf','kind':'rule_pdf','role':'cash_distribution_notice','file':'SH510500-2026-07-15.pdf','publication_day':'2026-07-08','host_role':'manager_notice_original_document_via_distributor_mirror_not_issuer_host'},
 {'id':'sse2026rule','url':'https://www.sse.com.cn/lawandrules/sselawsrules2025/fund/trading/c/10817739/files/7ffa42ba08bf4605a9e680bd38d452b4.docx','kind':'rule_docx','role':'SSE_2026_rule_effective_July6','file':'sse-2026-trading-rule.docx','publication_day':'2026-04-24','host_role':'SSE_original_rule_attachment'})

METHOD_FILES=('scripts/capture_etf_2026_notices_rules.py','scripts/capture_etf_action_sources.py',
 'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/fundamental_query_journal.py')

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);r=json.loads(Path(a.request).read_text())
 if (file_sha(a.request)!=a.expected_request_sha256 or r['sources']!=list(SOURCES)
  or r['maximum_http_queries']!=4 or r['max_attempts_per_identity']!=1 or r['minimum_interval_seconds']!=.3
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
  print('2026 cash notice/rule originals',m['captured_documents'],'/4; errors',list(m['errors']),flush=True)
  return 0 if m['captured_documents']==4 and not m['errors'] else 2
 finally:lock.close()

if __name__=='__main__':raise SystemExit(main())
