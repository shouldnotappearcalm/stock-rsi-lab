"""Four fixed interim2026 originals, after candidate freeze; no portfolio ROI."""
import argparse,fcntl,json
from pathlib import Path
from urllib.parse import urlencode
from scripts.capture_etf_action_sources import capture_sources,MAX_BODY
from scripts.fundamental_query_journal import file_sha

START='2026-01-01';END='2026-10-20';CODES=('SH510300','SH510500','SZ159915')
def history_url(code,mode='raw'):
 if code not in CODES or mode!='raw':raise ValueError('registered raw ETF only')
 params={'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116',
  'ut':'7eea3edcaed734bea9cbfc24409ed989','klt':'101','fqt':'0','beg':START.replace('-',''),'end':END.replace('-',''),
  'secid':('1.' if code.startswith('SH') else '0.')+code[2:]}
 return 'https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode(params)
SOURCES=tuple([{'id':c,'url':history_url(c),'kind':'price_json','role':'frozen_ETF_raw_interim2026','file':c+'-raw-wire.json'} for c in CODES]+[
 {'id':'sse2026closures','url':'https://www.sse.com.cn/disclosure/dealinstruc/closed/','kind':'rule_html','role':'official2026closure_crosscheck','file':'sse-2026-closures.html'}])
METHOD_FILES=('scripts/capture_etf_interim2026_sources.py','scripts/capture_etf_action_sources.py',
 'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/fundamental_query_journal.py')

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir);r=json.loads(Path(a.request).read_text())
 if (file_sha(a.request)!=a.sha256 or r['status']!='FROZEN_FOUR_INTERIM2026_ETF_SOURCE_IDENTITIES'
  or r['sources']!=list(SOURCES) or r['window']!=[START,END] or r['maximum_http_queries']!=4
  or r['max_attempts_per_identity']!=1 or r['minimum_interval_seconds']!=.3 or r['maximum_body_bytes']!=MAX_BODY
  or set(r['method_code_sha256'])!=set(METHOD_FILES) or any(file_sha(repo/n)!=h for n,h in r['method_code_sha256'].items())):
  raise ValueError('frozen interim source budget/method changed')
 for field,root in [('local_source_sha256',base),('public_evidence_sha256',repo)]:
  for n,h in r[field].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(root/n)!=h:raise ValueError('prerequisite source changed')
 out.mkdir(parents=True,exist_ok=True);lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  path=out/'request.json'
  if path.exists() and path.read_bytes()!=Path(a.request).read_bytes():raise ValueError('checkpoint request changed')
  if not path.exists():path.write_bytes(Path(a.request).read_bytes())
  m=capture_sources(out,r['sources'],a.sha256)
  print('Interim2026 original documents',m['captured_documents'],'/4; errors',list(m['errors']),'; no ROI',flush=True)
  return 0 if m['captured_documents']==4 and not m['errors'] else 2
 finally:lock.close()

if __name__=='__main__':raise SystemExit(main())
