"""Classify frozen development source windows; do not run a portfolio account."""
import argparse,json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
from scripts.tdx_history_checks import inspect_minutes
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.intraday_tape import aggregate_minutes
from stock_rsi.execution_diagnostics import buy_window_evidence

METHOD_FILES=('scripts/analyze_high52_unfilled_sources.py','scripts/tdx_history_checks.py',
 'src/stock_rsi/qlib_snapshot.py','src/stock_rsi/intraday_tape.py','src/stock_rsi/execution_diagnostics.py')

def main(argv=None):
 parser=argparse.ArgumentParser()
 for name in ('source-dir','provider-uri','request','expected-request-sha256','output'):parser.add_argument('--'+name,required=True)
 args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];source=Path(args.source_dir);output=Path(args.output)
 if output.exists() or sha256_file(args.request)!=args.expected_request_sha256:raise ValueError('probe output exists or frozen request changed')
 req=json.loads(Path(args.request).read_text());m=json.loads((source/'manifest.json').read_text())
 if (m['request_sha256']!=args.expected_request_sha256 or sha256_file(source/'request.json')!=args.expected_request_sha256
     or set(req['analysis_code_sha256'])!=set(METHOD_FILES)
     or any(sha256_file(root/n)!=h for n,h in req['analysis_code_sha256'].items())):raise ValueError('probe analysis/source identity changed')
 for name,h in m['artifact_sha256'].items():
  if sha256_file(source/name)!=h:raise ValueError('captured source artifact changed')
 for name,h in req['qlib_metadata_sha256'].items():
  if sha256_file(Path(args.provider_uri)/name)!=h:raise ValueError('price metadata changed')
 for name,h in req['qlib_feature_sha256'].items():
  if sha256_file(Path(args.provider_uri)/name)!=h:raise ValueError('frozen price source changed')
 snapshot=QlibSnapshot(args.provider_uri);rows=[]
 for code,day in req['pairs']:
  if not '2024-01-02'<=day<='2025-12-31':raise ValueError('analysis source cutoff crossed')
  filename=code+'-'+day+'.json';daily=json.loads((source/'daily'/filename).read_text());packet=json.loads((source/'sessions'/filename).read_text())
  if any(p['instrument']!=code or p['requested_day']!=day for p in (daily,packet)):raise ValueError('source identity mismatch')
  bar=daily['bar'];record=packet.get('methods',{}).get('minutes.history',packet)
  row={'instrument':code,'day':day,'raw_state':{'tradestatus':bar['tradestatus'],'isST':bar['isST']},
       'source_daily_sha256':m['artifact_sha256']['daily/'+filename],'source_minute_sha256':m['artifact_sha256']['sessions/'+filename]}
  try:
   if record['status']!='RESPONSE_CAPTURED':raise ValueError('minute source unavailable')
   facts=inspect_minutes(code,day,record['response'],bar)
   if bar['tradestatus']!='1' or bar['isST']!='0':
    row.update(status='HALTED_OR_SPECIAL_STATUS_UNSUPPORTED',minute_source_diagnostics=facts);rows.append(row);continue
   if not facts['last_close_matches'] or facts['traded_points_outside_daily_range']:raise ValueError('minute/day price conflict')
   windows=aggregate_minutes(code,date.fromisoformat(day),record['response']['points'])
   if sum(w['volume_lower_shares'] for w in windows)>int(bar['volume']):raise ValueError('stressed minute volume above raw whole day')
   factor=snapshot.value(code,'factor',day)
   if factor is None or factor<=0:raise ValueError('positive execution normalization factor required')
   checked={}
   for f in ('open','high','low','close'):
    normalized=snapshot.value(code,f,day)
    if normalized is None or abs(normalized/factor-float(bar[f]))>.005:raise ValueError('independent raw-day/Qlib price mismatch')
    checked[f]=str(bar[f])
   index=snapshot.calendar.index(date.fromisoformat(day));prior=snapshot.calendar[index-1].isoformat()
   previous=snapshot.value(code,'close',prior);opening=snapshot.value(code,'open',day)
   change=opening/previous-1
   row.update(status='SOURCE_WINDOW_EVIDENCE_COMPLETE',cross_source_daily_prices=checked,
    minute_source_diagnostics=facts,qlib_prior_session=prior,qlib_open_change_pct=change*100,
    qlib_open_guard_blocks_buy=change>=.095,
    evidence_by_participation_bps={str(p):buy_window_evidence(windows,bar,p) for p in (100,500,1000)})
  except (ValueError,KeyError,TypeError,ZeroDivisionError) as exc:row.update(status='SOURCE_REJECTED',error=str(exc))
  rows.append(row)
 counts=dict(Counter(r['status'] for r in rows));complete=[r for r in rows if r['status']=='SOURCE_WINDOW_EVIDENCE_COMPLETE']
 result={'status':'HIGH52_UNFILLED_SOURCE_PROBE_COMPLETE','pairs':35,'request_sha256':args.expected_request_sha256,
  'capture_manifest_sha256':sha256_file(source/'manifest.json'),'analysis_code_sha256':req['analysis_code_sha256'],'status_counts':counts,
  'all_source_pairs_admitted':len(complete)==35,'source_open_guard_blocked_buy_pairs':sum(r['qlib_open_guard_blocks_buy'] for r in complete),
  'pairs_with_candidate_windows_by_participation_bps':{str(p):sum(r['evidence_by_participation_bps'][str(p)]['candidate_windows']>0 for r in complete) for p in (100,500,1000)},
  'results':rows,'original_high52_screen_gate_unchanged':'REJECTED','new_portfolio_account_run':False,
  'actual_fills_verified':False,'portfolio_cash_and_parent_quantities_not_simulated':True,
  'no_day_closing_price_substituted_for_a_trade':True,'historical_arrival_verified':False,'queue_and_impact_calibrated':False,
  '2026_strategy_returns_queried':False,'objective_achieved':False}
 output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('results','analysis_code_sha256')},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
