"""Capture five exact noncash implementation notices, using unchanged HTTP journal."""
import argparse,json
from pathlib import Path
from scripts.capture_low_beta60_corporate_2026 import capture_documents
from scripts.capture_budgeted_corporate_notices_pre2026 import read_wire
from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
METHODS=('scripts/capture_value_momentum_noncash_2026.py','scripts/capture_low_beta60_corporate_2026.py','scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/audit_cninfo_report_admission.py','scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py')
def main():
 p=argparse.ArgumentParser()
 for n in ('request','expected-request-sha256','output-dir'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args();repo=Path(__file__).resolve().parents[1]
 if sha256_file(a.request)!=a.expected_request_sha256:raise ValueError('frozen request changed')
 r=json.loads(Path(a.request).read_bytes())
 if r['maximum_http_queries']!=5 or len(r['documents'])!=5 or r['max_attempts_per_identity']!=1 or set(r['method_code_sha256'])!=set(METHODS):raise ValueError('fixed five-document request required')
 for f,h in r['method_code_sha256'].items():
  if sha256_file(repo/f)!=h:raise ValueError('frozen source method changed')
 if a.preflight_only:print('five exact noncash original requests authenticated; no HTTP');return
 result=capture_documents(r,repo,Path(a.output_dir),read_wire,request_sha=a.expected_request_sha256)
 print('five noncash originals',len(result['documents']),'errors',len(result['errors']),flush=True)
 return 0 if result['capture_complete'] else 2
if __name__=='__main__':raise SystemExit(main())
