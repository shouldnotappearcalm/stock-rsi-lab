"""Read-only original-packet inventory after the frozen formation extension."""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
base = Path(args.source_root)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text())
sources = ('low-risk-raw-account-data-20261017', 'szse-value-raw-full-20261017', 'reversal-raw-full-20261017')
formation = base / 'low-beta60-calendar-extension-formations-20261021'
assert sha(formation / 'summary.json') == 'd70ef4466c69666314de6a2c4cb4c4f9a4e848ba8ed70f5ee95b2e8faa25ea90'
summary = read(formation / 'summary.json')
assert all(sha(formation / n) == h for n, h in summary['artifact_sha256'].items())
audit = base / 'low-beta60-calendar-extension-independent-audit-20261021.json'
assert sha(audit) == '4e1b309a7a1d7c26fb8a80e0a863221ea9869dda307dd5e1e759ecfa79e8e2eb'
assert read(audit)['old24_targets_and_receipts_byte_identical'] is True
targets = read(formation / 'targets.json')['low_beta60']
codes = sorted({c for t in targets.values() for c in t['weights']})
assert len(targets) == 34 and len(codes) == 79
reference = base / sources[0] / 'calendar.json'
sessions = [d for d in read(reference)['sessions'] if '2023-12-29' <= d <= '2026-10-13']
assert sessions == sorted(set(sessions)) and sessions[0] == '2023-12-29' and sessions[-1] == '2026-10-13'
original = base / 'low-beta60-raw-dev-20261021'
old_manifest = read(original / 'manifest.json')
assert sha(original / 'manifest.json') == '411e2abe02ebf914c809d6b5acb9b7e2fabacafe7dc88081b980787fb0cd8613'
manifests = {s: read(base / s / 'manifest.json') for s in sources}
assert all(m['calendar_sha256'] == sha(base / s / 'calendar.json') for s, m in manifests.items())
assert all([d for d in read(base / s / 'calendar.json')['sessions'] if d <= '2026-10-13'] == sessions for s in sources)


def core(rows):
    return [[r['date'], r['code'], *[str(Decimal(r[f]).normalize()) if r[f] else ''
             for f in ('open', 'high', 'low', 'close', 'preclose', 'volume', 'amount')],
             r['tradestatus'], r['isST']] for r in rows]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


items = {}
fresh = []
conflicts = []
prefix_conflicts = []
for code in codes:
    old = None
    if code in old_manifest['per_code_sha256']:
        path = original / 'codes' / (code + '.json')
        assert sha(path) == old_manifest['per_code_sha256'][code]
        old = read(path)
    choices = []
    for s, m in manifests.items():
        if code not in m['per_code_sha256']:
            continue
        path = base / s / 'codes' / (code + '.json')
        assert sha(path) == m['per_code_sha256'][code]
        packet = read(path)
        assert packet['instrument'] == code
        rows = [r for r in packet['bars'] if sessions[0] <= r['date'] <= sessions[-1]]
        assert [r['date'] for r in rows] == sorted(set(r['date'] for r in rows))
        for r in rows:
            assert r['code'] == code[:2].lower() + '.' + code[2:]
        prefix = [r for r in rows if r['date'] <= '2025-12-31']
        distribution_prefix = [r for r in packet['distributions'] if r['dividOperateDate'] <= '2025-12-31']
        adjustment_prefix = [r for r in packet['adjustments'] if r['dividOperateDate'] <= '2025-12-31']
        choices.append({'source_directory': s, 'original_packet_sha256': m['per_code_sha256'][code],
                        'original_window': packet['window'], 'full_requested_calendar': [r['date'] for r in rows] == sessions,
                        'missing_sessions': sorted(set(sessions) - {r['date'] for r in rows}),
                        'full_window_raw_core_sha256': fingerprint(core(rows)),
                        'original_pre2026_raw_core_matches': None if old is None else core(prefix) == core(old['bars']),
                        'original_pre2026_distribution_rows_match': None if old is None else distribution_prefix == old['distributions'],
                        'original_pre2026_adjustment_rows_match': None if old is None else adjustment_prefix == old['adjustments'],
                        'vendor2026_distribution_rows': sum('2026-01-01' <= r['dividOperateDate'] <= sessions[-1] for r in packet['distributions']),
                        'vendor2026_adjustment_rows': sum('2026-01-01' <= r['dividOperateDate'] <= sessions[-1] for r in packet['adjustments'])})
    if not choices:
        fresh.append(code)
    if len({c['full_window_raw_core_sha256'] for c in choices}) > 1:
        conflicts.append(code)
    if any(c[k] is False for c in choices for k in ('original_pre2026_raw_core_matches',
            'original_pre2026_distribution_rows_match', 'original_pre2026_adjustment_rows_match')):
        prefix_conflicts.append(code)
    reusable = [c for c in choices if c['full_requested_calendar'] and all(c[k] is not False for k in (
                'original_pre2026_raw_core_matches', 'original_pre2026_distribution_rows_match', 'original_pre2026_adjustment_rows_match'))]
    items[code] = {'status': 'AUTHENTICATED_CACHE_NOT_ADMITTED' if reusable else 'RAW_SOURCE_GAP_OR_CONTRADICTION',
                   'priority_route': reusable[0]['source_directory'] if reusable else None, 'choices': choices}
result = {'status': 'LOW_BETA60_EXTENSION_RAW_SOURCE_INVENTORY_NOT_REPLAY_ADMISSION',
          'inventory_code_sha256': sha(__file__), 'formation_summary_sha256': sha(formation / 'summary.json'),
          'target_sha256': sha(formation / 'targets.json'), 'formation_independent_audit_sha256': sha(audit),
          'window': [sessions[0], sessions[-1]], 'calendar_sessions': len(sessions), 'names': len(codes),
          'source_priority_fixed_before_inventory': list(sources),
          'source_manifest_sha256': {s: sha(base / s / 'manifest.json') for s in sources},
          'source_calendar_sha256': {s: sha(base / s / 'calendar.json') for s in sources},
          'original_pre2026_raw_manifest_sha256': sha(original / 'manifest.json'),
          'names_with_full_cache_and_original_prefix': sum(v['priority_route'] is not None for v in items.values()),
          'codes_with_no_cached_packet': fresh, 'cross_cache_raw_core_conflict_codes': conflicts,
          'original_pre2026_prefix_conflict_codes': prefix_conflicts,
          'codes_needing_source_or_conflict_resolution': [c for c, v in items.items() if not v['priority_route']],
          'items': items, 'new_network_queries': 0, 'source_admitted_for_account_replay': False,
          'primary2026_distribution_proofs_reviewed': False, 'historical_arrival_verified': False,
          'portfolio_returns_computed': False, 'objective_achieved': False}
with Path(args.output).open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print('raw cache inventory', result['names_with_full_cache_and_original_prefix'], '/', len(codes),
      'no packet', len(fresh), 'cross-cache conflicts', len(conflicts), 'original-prefix conflicts', len(prefix_conflicts), 'no ROI')
