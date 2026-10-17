"""Read-only source comparison; no renormalization and no strategy imports."""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

BASE = Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
SINA = Path('/Users/calm/.cache/stock-rsi-sources/execution-rules-20261017/sina-daily-SH600008.response')
OUTPUT = Path('experiments/qlib/low-risk-minute-source-quality.json')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert not OUTPUT.exists(), 'never overwrite source comparison evidence'
packets = {p.stem: json.loads(p.read_text()) for p in (BASE/'low-risk-raw-account-data-20261017/codes').glob('*.json')}
bars = {code: {row['date']: row for row in packet['bars']} for code, packet in packets.items()}
counts = Counter(); examples = []
for path in sorted((BASE/'low-risk-execution-tape-20261017/sessions').glob('*.json')):
    packet = json.loads(path.read_text()); code = packet['instrument']; day = packet['session']
    daily = bars[code][day]; rows = packet['rows']; year = day[:4]
    counts[(year, 'requested_sessions')] += 1
    if not daily['volume']:
        counts[(year, 'daily_volume_unknown')] += 1
        continue
    assert len(rows) == 48
    total = sum((Decimal(row['volume']) for row in rows), Decimal(0))
    equal = total == Decimal(daily['volume'])
    counts[(year, 'known_daily_volume_sessions')] += 1
    counts[(year, 'exact_volume_matches')] += equal
    counts[(year, 'volume_mismatches')] += not equal
    counts[(year, 'first_open_matches')] += Decimal(rows[0]['open']) == Decimal(daily['open'])
    counts[(year, 'last_close_matches')] += Decimal(rows[-1]['close']) == Decimal(daily['close'])
    if not equal and len(examples) < 5:
        examples.append({'instrument': code, 'day': day, 'minute_total_volume': str(total), 'daily_volume': daily['volume']})
sina = {row['day']: row for row in json.loads(SINA.read_text())}
compared = 0; missing = []; differences = []
for row in packets['SH600008']['bars']:
    if row['tradestatus'] != '1': continue
    day = row['date']
    if day not in sina:
        missing.append(day); continue
    compared += 1
    for field in ('open', 'high', 'low', 'close', 'volume'):
        if Decimal(row[field]) != Decimal(sina[day][field]):
            differences.append({'day': day, 'field': field, 'baostock': row[field], 'sina': sina[day][field]})
result = {'status': 'OLDER_MINUTE_VOLUME_UNRESOLVED_NO_TOLERANCE_RELAXATION',
          'by_year': {year: {name: counts[(year, name)] for name in ('requested_sessions', 'daily_volume_unknown',
             'known_daily_volume_sessions', 'exact_volume_matches', 'volume_mismatches', 'first_open_matches', 'last_close_matches')}
             for year in ('2024', '2025', '2026')}, 'mismatch_examples': examples,
          'independent_daily_sample': {'instrument': 'SH600008', 'selection': 'first chronological shared frozen-order example, not a sampled policy winner',
             'sessions_compared': compared, 'fields': ['open','high','low','close','volume'], 'missing_sessions': missing,
             'differences': differences, 'response_sha256': sha(SINA),
             'source_url': 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600008&scale=240&ma=no&datalen=1023',
             'scope': 'One-security daily sample only, not validation of all securities or minute/auction volumes'},
          'audit_script_sha256': sha(Path(__file__)),
          'tape_manifest_sha256': sha(BASE/'low-risk-execution-tape-20261017/manifest.json'),
          'raw_manifest_sha256': sha(BASE/'low-risk-raw-account-data-20261017/manifest.json'),
          'source_values_renormalized': False, 'auction_volume_verified': False, 'objective_achieved': False}
OUTPUT.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
