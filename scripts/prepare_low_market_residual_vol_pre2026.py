"""One frozen, physically pre2026 formation-only low-risk variant trial."""
import argparse,json
from pathlib import Path
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_qlib_low_risk_pre2026 import input_hashes,parse_memberships
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.low_market_residual_vol import START,END,FAMILIES,CONTROL,build_targets

DESIGN='docs/research/low-market-residual-vol1m-pre2026-design-2026-10-21.md'
OUTPUT='low-market-residual-vol1m-pre2026-formations-20261021'
METHOD_FILES=('scripts/prepare_low_market_residual_vol_pre2026.py','src/stock_rsi/low_market_residual_vol.py',
 'src/stock_rsi/prior_close_orders.py','src/stock_rsi/qlib_snapshot.py',
 'scripts/run_qlib_low_risk_pre2026.py','scripts/run_cninfo_orj_signal_pre2026.py',
 'scripts/prepare_qlib_master_market_pre2026.py')
STATUS='FROZEN_SINGLE_LOW_MARKET_RESIDUAL_VOL1M_FORMATIONS_ONLY'


def validate_request(request):
 if (request['status']!=STATUS or request['families']!=list(FAMILIES) or request['descriptive_controls']!=['eligible_equal_weight',CONTROL]
  or request['candidate_budget']!=1 or request['window']!=[START,END] or request['output_directory']!=OUTPUT
  or request['new_source_queries']!=0 or request['portfolio_returns_to_compute'] is not False
  or request['2026_market_values_to_query'] is not False or set(request['method_code_sha256'])!=set(METHOD_FILES)):
  raise ValueError('single fixed pre2026 formation-only trial required')


def authenticate(provider,repo,request):
 validate_request(request)
 if sha256_file(repo/DESIGN)!=request['design_sha256']:raise ValueError('pre-outcome research design changed')
 for n,h in request['method_code_sha256'].items():
  if sha256_file(repo/n)!=h:raise ValueError('frozen formation method changed')
 if sha256_file(provider/'manifest.json')!=request['provider_manifest_sha256']:raise ValueError('physical provider changed')
 m=json.loads((provider/'manifest.json').read_bytes())
 if m['all_output_values_at_or_before']!=END or m['output_calendar_end']!=END:raise ValueError('all quote values must be physically capped at2025')
 for name,meta in m['per_feature'].items():
  if Path(name).is_absolute() or '..' in Path(name).parts or sha256_file(provider/name)!=meta['sha256'] or meta['last_date']>END:
   raise ValueError('complete fixed pre2026 feature bytes required')
 members=parse_memberships((provider/'instruments/csi500.txt').read_text())
 if input_hashes(provider,members)!=request['input_sha256']:raise ValueError('complete historical prices/calendar/membership changed')
 snapshot=QlibSnapshot(provider)
 if snapshot.calendar[-1].isoformat()!=END:raise ValueError('quote API calendar crosses2025')
 return snapshot,members


def main(argv=None):
 p=argparse.ArgumentParser()
 for name in ('provider-uri','request','expected-request-sha256','output-dir'):p.add_argument('--'+name,required=True)
 p.add_argument('--source-preflight-only',action='store_true');a=p.parse_args(argv)
 out,provider=Path(a.output_dir),Path(a.provider_uri);repo=Path(__file__).resolve().parents[1]
 if out.exists() or out.name!=OUTPUT or sha256_file(a.request)!=a.expected_request_sha256:raise ValueError('fixed new output and external request SHA required')
 request=json.loads(Path(a.request).read_bytes());snapshot,members=authenticate(provider,repo,request)
 if a.source_preflight_only:
  print('physical pre2026 source authenticated; no formation/returns/output');return 0
 out.mkdir(parents=True)
 try:
  targets,receipts=build_targets(snapshot,members)
  if (len(receipts)!=24 or set(targets)!={*FAMILIES,'eligible_equal_weight',CONTROL}
    or any(len(t)!=24 for t in targets.values())
    or any(row['latest_factor_price_read']!=row['formation_asof'] or row['formation_asof']>=row['execution_session'] for row in receipts)):
   raise ValueError('all24 bounded monthly formations required')
  for name,value in [('targets.json',targets),('formation_receipts.json',receipts)]:
   with(out/name).open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
  # Recheck all original source/method bytes after forming; no account was used.
  authenticate(provider,repo,request)
  if sha256_file(a.request)!=a.expected_request_sha256:raise ValueError('external formation request changed')
  summary={'status':'LOW_MARKET_RESIDUAL_VOL1M_24_PRE2026_FORMATIONS_ONLY_NO_RETURNS',
   'request_sha256':a.expected_request_sha256,'method_code_sha256':request['method_code_sha256'],
   'provider_manifest_sha256':request['provider_manifest_sha256'],'input_sha256':request['input_sha256'],
   'formations':24,'candidate_budget':1,'economic_family':'EXISTING_LOW_RISK_LOTTERY_VARIANT',
   'eligible_range':[min(x['eligible'] for x in receipts),max(x['eligible'] for x in receipts)],
   'artifact_sha256':{n:sha256_file(out/n) for n in ('targets.json','formation_receipts.json')},
   'source_queries':0,'portfolio_returns_computed':False,'2026_market_values_queried':False,
   'historical_arrival_verified':False,'objective_achieved':False}
  with(out/'summary.json').open('x') as f:json.dump(summary,f,indent=2);f.write('\n')
  print('24one-month market-residual-vol formations; no portfolio ROI');return 0
 except Exception as error:
  with(out/'failure.json').open('x') as f:json.dump({'error_type':type(error).__name__,'error':str(error),
   'portfolio_returns_computed':False,'2026_market_values_queried':False},f,indent=2);f.write('\n')
  raise


if __name__=='__main__':raise SystemExit(main())
