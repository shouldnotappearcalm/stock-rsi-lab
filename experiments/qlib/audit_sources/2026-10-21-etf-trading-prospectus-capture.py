"""Two fixed pre2026 product documents; no returns or price requests."""
import argparse,json
from pathlib import Path
from scripts.capture_etf_action_sources import capture_sources
from scripts.fundamental_query_journal import file_sha
SOURCES=[{'id':'SH510300_trading','url':'https://static.cninfo.com.cn/finalpage/2024-06-01/1220228349.PDF','file':'SH510300-2024-prospectus.pdf','kind':'rule_pdf','role':'fund_prospectus'},
 {'id':'SH510500_trading','url':'https://www.nffund.com/main/files/2024/11/20/990043127212.pdf','file':'SH510500-2024-prospectus.pdf','kind':'rule_pdf','role':'fund_prospectus'}]
p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha256',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args();r=json.loads(Path(a.request).read_text())
if file_sha(a.request)!=a.sha256 or r['sources']!=SOURCES or r['maximum_queries']!=2 or r['max_attempts']!=1:raise ValueError('fixed two-document budget changed')
for n,h in r['method_code_sha256'].items():
 if file_sha(n)!=h:raise ValueError('frozen transport identity changed')
m=capture_sources(Path(a.output_dir),SOURCES,a.sha256)
print('Trading prospectus originals',m['captured_documents'],'/2; errors',list(m['errors']))
raise SystemExit(0 if m['captured_documents']==2 and not m['errors'] else 2)
