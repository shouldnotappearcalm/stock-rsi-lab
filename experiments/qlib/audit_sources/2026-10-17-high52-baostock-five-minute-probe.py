"""One explicitly dated raw five-minute query. No interpolation, orders or ROI."""
import hashlib,json,socket
from datetime import datetime,timezone
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
import baostock as bs
from scripts.capture_low_risk_execution_tape import FIELDS,validate_minutes
from scripts.capture_low_risk_raw_account_data import query_rows
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('experiments/qlib/high52-baostock-five-minute-probe-request.json')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=json.loads(R.read_text());assert p['pair']==['SH603056','2025-06-03'] and p['maximum_history_queries']==1
assert p['frequency']=='5' and p['adjustflag']=='3' and version('baostock')==p['package_version']
assert sha(Path(__file__))==p['capture_code_sha256']
assert sha(Path('scripts/capture_low_risk_execution_tape.py'))==p['source_validator_sha256']
source=B/'high52-unfilled-source-probe-20261017/daily/SH603056-2025-06-03.json';assert sha(source)==p['reference_daily_packet_sha256']
daily=json.loads(source.read_text())['bar'];out=B/'high52-baostock-five-minute-probe-20261017';assert not out.exists();out.mkdir()
packet={'instrument':'SH603056','session':'2025-06-03','query_window':['2025-06-03','2025-06-03'],'frequency':'5','adjustflag':'3',
 'started_at':datetime.now(timezone.utc).isoformat(),'request_sha256':sha(R),'reference_daily_packet_sha256':sha(source)}
socket.setdefaulttimeout(20)
try:
 if bs.login().error_code!='0':raise RuntimeError('source login failed')
 fields,raw=query_rows(bs.query_history_k_data_plus('sh.603056',','.join(FIELDS),start_date='2025-06-03',end_date='2025-06-03',frequency='5',adjustflag='3'))
 packet.update(status='RESPONSE_CAPTURED',fields=fields,raw_rows=raw)
 try:
  rows,complete=validate_minutes('SH603056','2025-06-03',fields,raw)
  checks={'complete_48_labels':complete,'first_open_matches':bool(rows) and Decimal(rows[0]['open'])==Decimal(daily['open']),
   'highest_matches':bool(rows) and max(Decimal(r['high']) for r in rows)==Decimal(daily['high']),
   'lowest_matches':bool(rows) and min(Decimal(r['low']) for r in rows)==Decimal(daily['low']),
   'last_close_matches':bool(rows) and Decimal(rows[-1]['close'])==Decimal(daily['close']),
   'total_volume_matches':bool(rows) and sum(Decimal(r['volume']) for r in rows)==Decimal(daily['volume'])}
  packet.update(rows=rows,source_checks=checks,admitted_as_reported_5min_OHLCV=all(checks.values()),
   total_5min_reported_volume=str(sum(Decimal(r['volume']) for r in rows)),daily_reported_volume=daily['volume'])
 except (ValueError,KeyError) as exc:packet.update(admitted_as_reported_5min_OHLCV=False,validation_error=str(exc))
except Exception as exc:packet.update(status='REQUEST_FAILED',error_type=type(exc).__name__,error=str(exc)[:300],admitted_as_reported_5min_OHLCV=False)
finally:bs.logout()
packet.update(original_TDX_failure_unchanged=True,one_minute_series_created=False,interchangeable_with_240_minute_points=False,
 source_is_a_fill_verification=False,historical_arrival_verified=False,new_portfolio_account_run=False,**{'2026_market_values_queried':False,'objective_achieved':False})
path=out/'packet.json';path.write_text(json.dumps(packet,indent=2)+'\n')
summary={k:v for k,v in packet.items() if k not in ('rows','raw_rows')};summary['packet_sha256']=sha(path)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
