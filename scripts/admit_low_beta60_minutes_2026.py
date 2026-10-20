"""Frozen source-only checks for754newyear tapes, retaining old1332 untouched."""
import argparse
import json
from collections import Counter
from pathlib import Path

from scripts.capture_low_beta60_minutes_2026 import authenticate_inputs
from scripts.fundamental_query_journal import file_sha, digest
from scripts.low_beta60_2026_minute_sources import inspect_packet, verify_receipt


def main(argv=None):
    p = argparse.ArgumentParser()
    for n in ('source-root', 'capture-dir', 'plan', 'expected-plan-sha256', 'expected-capture-manifest-sha256', 'output-dir'):
        p.add_argument('--' + n, required=True)
    a = p.parse_args(argv)
    base, repo, capture, out = Path(a.source_root), Path(__file__).resolve().parents[1], Path(a.capture_dir), Path(a.output_dir)
    if out.exists():
        raise ValueError('preserve source validation attempt')
    plan, reused, fresh, bars = authenticate_inputs(base, repo, a.plan, a.expected_plan_sha256)
    if file_sha(capture / 'manifest.json') != a.expected_capture_manifest_sha256:
        raise ValueError('externally anchored captured source manifest changed')
    m = json.loads((capture / 'manifest.json').read_text())
    if (file_sha(capture / 'plan.json') != a.expected_plan_sha256 or m['plan_sha256'] != a.expected_plan_sha256
            or m['capture_request_sha256'] != file_sha(capture / 'capture_request.json')
            or json.loads((capture / 'capture_request.json').read_text()) != {'reused': reused, 'fresh': fresh}
            or m['reused_session_provenance'] != reused or m['requested'] != 754
            or m['captured'] != len(m['per_session_sha256'])):
        raise ValueError('capture source protocol or fixed partition changed')
    expected = set(reused) | {c + '-' + d + '.json' for c, d in fresh}
    if not set(m['per_session_sha256']) <= expected or {p.name for p in (capture / 'sessions').iterdir()} != set(m['per_session_sha256']):
        raise ValueError('unbound source packet or unexpected capture identity')
    snapshots = list(capture.glob('capture-snapshot-*.json'))
    if len(snapshots) != 1 or snapshots[0].name != 'capture-snapshot-' + digest(m) + '.json' or json.loads(snapshots[0].read_text()) != m:
        raise ValueError('immutable captured source snapshot changed')
    keys = {digest({'method': 'minutes.history', 'instrument': c, 'requested_day': d,
                    'host': plan['host'], 'include_raw': True}) for c, d in fresh}
    folders = list((capture / 'queries').iterdir())
    if any(not f.is_dir() or f.name not in keys or {p.name for p in f.iterdir()} != {'request.json','reserved-1.json','response-1.json'} for f in folders):
        raise ValueError('source query identity or one-attempt file set changed')
    if len(folders) != m['fresh_query_reservations'] or len(folders) != m['fresh_query_responses_preserved'] or len(folders) > 247:
        raise ValueError('reserved source budget or response count changed')
    rows = []
    for name in sorted(expected):
        code, day = name[:-5].split('-', 1)
        r = {'instrument': code, 'day': day}
        try:
            if name not in m['per_session_sha256']:
                raise ValueError('source not captured')
            f = capture / 'sessions' / name
            if file_sha(f) != m['per_session_sha256'][name]:
                raise ValueError('captured source packet bytes changed')
            packet = json.loads(f.read_text())
            if name in reused:
                if file_sha(f) != reused[name]['sha256']:
                    raise ValueError('reused output differs from original source bytes')
                r['origin'] = reused[name]
            else:
                verify_receipt(capture, code, day, packet, plan['host'])
                r['origin'] = 'FROZEN_FRESH2026_QUERY'
            r.update(inspect_packet(code, day, packet, bars[code][day]), source_sha256=file_sha(f))
        except (ValueError, KeyError, ArithmeticError, OSError) as exc:
            r.update(status='SOURCE_REJECTED', error_type=type(exc).__name__, error=str(exc))
        rows.append(r)
    counts = dict(Counter(r['status'] for r in rows))
    passed = (counts == {'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE': 754} and m['complete_capture'] is True
              and m['abnormal_exit'] is None and not m['stopped_after_consecutive_source_failures']
              and len(folders) == 247 and m['response_status_counts'] == {'RESPONSE_CAPTURED': 754})
    out.mkdir(parents=True)
    (out / 'details.json').write_text(json.dumps({'sessions': rows}, indent=2) + '\n')
    result = {'status': 'LOW_BETA60_2026_MINUTE_SOURCE_VALIDATION_COMPLETE', 'plan_sha256': a.expected_plan_sha256,
        'capture_manifest_sha256': a.expected_capture_manifest_sha256, 'details_sha256': file_sha(out / 'details.json'),
        'required_active_sessions': 754, 'reused_packets': 507, 'fresh_reservations': len(folders), 'status_counts': counts,
        'admitted_for_reconstructed_execution': passed, 'combined_source_pairs_including_original1332': 2086 if passed else None,
        'original1332_source_bytes_rechecked_unchanged': True,
        'exact_share_total_matches': sum(r.get('facts', {}).get('exact_total_shares_match') is True for r in rows),
        'nearest_hand_total_matches_diagnostic_only': sum(r.get('facts', {}).get('nearest_hand_daily_total_match_diagnostic_only') is True for r in rows),
        'exact_share_precision_certified': False, 'historical_arrival_verified': False, 'sdk_date_echo_authenticated': False,
        'queue_and_impact_calibrated': False, 'full_corporate_actions_certified': False,
        'portfolio_returns_computed': False, 'candidate_promoted': False, 'objective_achieved': False,
        'exceptions': [r for r in rows if r['status'] != 'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE']}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print('2026 minute source validation', counts, 'original1332unchanged; no ROI', flush=True)
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
