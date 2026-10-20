"""One additionally budgeted quote-header attempt for each failed ETF URL."""
import argparse,base64,fcntl,json
from urllib.error import HTTPError
from urllib.request import Request,build_opener
from scripts.capture_budgeted_corporate_notices_pre2026 import NoRedirect
from pathlib import Path
from urllib.parse import urlencode
from scripts.capture_etf_action_sources import capture_sources,MAX_BODY
from scripts.fundamental_query_journal import file_sha

from scripts.capture_etf_interim2026_sources import START,END,SOURCES as FIRST_SOURCES
SOURCES=FIRST_SOURCES[:3]

METHOD_FILES=('scripts/capture_etf_interim2026_quote_retry.py','scripts/capture_etf_interim2026_sources.py','scripts/capture_etf_action_sources.py',
 'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/fundamental_query_journal.py')

def read_wire(url,allowed):
    if url not in allowed or not url.startswith('https://'):raise ValueError('unregistered source URL')
    req=Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'})
    try:response=build_opener(NoRedirect()).open(req,timeout=20)
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
    raw=b''.join(chunks);length=response.headers.get('Content-Length')
    if error_type is None and length is not None:
        try:expected=int(length)
        except ValueError:expected=-1
        if expected<0 or len(raw)!=expected:error_type,error='ContentLengthMismatch','incomplete HTTP bytes'
    return ['http_response'],[{'status':response.code,'final_url':response.geturl(),'content_type':response.headers.get('Content-Type',''),
        'body_base64':base64.b64encode(raw).decode(),'body_truncated':len(raw)>MAX_BODY,
        'body_complete':error_type is None and len(raw)<=MAX_BODY,'read_error_type':error_type,'read_error':error}]



def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir);r=json.loads(Path(a.request).read_text())
 if (file_sha(a.request)!=a.sha256 or r['status']!='FROZEN_THREE_QUOTE_HEADER_ADDITIONAL_ETF_ATTEMPTS'
  or r['sources']!=list(SOURCES) or r['window']!=[START,END] or r['maximum_http_queries']!=3
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
  m=capture_sources(out,r['sources'],a.sha256,fetch=read_wire)
  print('Quote-header interim2026 originals',m['captured_documents'],'/3; errors',list(m['errors']),'; no ROI',flush=True)
  return 0 if m['captured_documents']==3 and not m['errors'] else 2
 finally:lock.close()

if __name__=='__main__':raise SystemExit(main())
