"""Formation-only frozen stage: no portfolio backtest or2026 market reads."""
import argparse,json
from pathlib import Path
from scripts.run_qlib_low_beta60_pre2026 import METHOD_FILES as RUN_FILES
from scripts.run_qlib_low_risk_pre2026 import parse_memberships,input_hashes
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from stock_rsi.low_beta60 import build_targets
from stock_rsi.qlib_snapshot import QlibSnapshot
METHOD_FILES=(*RUN_FILES,'scripts/prepare_low_beta60_pre2026.py')

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','sha256','provider-uri','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(a.output_dir);r=json.loads(Path(a.request).read_text())
 if out.exists():raise ValueError('preserve formation outputs')
 if (sha256_file(a.request)!=a.sha256 or r['status']!='FROZEN_LOW_BETA60_FORMATIONS_ONLY'
  or set(r['method_code_sha256'])!=set(METHOD_FILES) or any(sha256_file(root/n)!=h for n,h in r['method_code_sha256'].items())):raise ValueError('frozen formation method changed')
 memberships=parse_memberships((Path(a.provider_uri)/'instruments/csi500.txt').read_text())
 if input_hashes(a.provider_uri,memberships)!=r['input_sha256']:raise ValueError('input snapshot changed')
 if sha256_file(root/r['design_file'])!=r['design_sha256']:raise ValueError('registered design changed')
 targets,receipts=build_targets(QlibSnapshot(a.provider_uri),memberships)
 if len(receipts)!=24 or any(x['latest_factor_price_read']!=x['formation_asof'] for x in receipts):raise ValueError('24 bounded monthly formations required')
 out.mkdir(parents=True)
 for name,value in [('targets.json',targets),('formation_receipts.json',receipts)]:
  with (out/name).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
 m={'status':'LOW_BETA60_FORMATIONS_ONLY_NO_PORTFOLIO_ROI','request_sha256':a.sha256,'method_code_sha256':r['method_code_sha256'],
  'input_sha256':r['input_sha256'],'formations':24,'window':['2024-01-02','2025-12-31'],'candidate_budget':1,
  'eligible_range':[min(x['eligible'] for x in receipts),max(x['eligible'] for x in receipts)],
  'target_sha256':sha256_file(out/'targets.json'),'receipt_sha256':sha256_file(out/'formation_receipts.json'),
  'network_queries':0,'portfolio_returns_computed':False,'2026_market_values_queried':False,'sealed_evidence':False,'objective_achieved':False}
 with (out/'summary.json').open('x') as f:json.dump(m,f,ensure_ascii=False,indent=2);f.write('\n')
 print('lowbeta60 bounded formations',24,'eligible',m['eligible_range'],'no portfolioROI',flush=True);return 0
if __name__=='__main__':raise SystemExit(main())
