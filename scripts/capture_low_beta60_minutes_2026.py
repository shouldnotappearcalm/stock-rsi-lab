"""Capture247 missing2026sources, reusing507; do not touch original1332."""
import argparse
import json
from importlib.metadata import version
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from scripts.low_beta60_2026_minute_sources import capture_extension, inspect_packet

METHOD_FILES = ('scripts/capture_low_beta60_minutes_2026.py', 'scripts/low_beta60_2026_minute_sources.py',
    'scripts/admit_low_beta60_minutes_2026.py', 'scripts/fundamental_query_journal.py',
    'scripts/tdx_history_checks.py', 'src/stock_rsi/intraday_tape.py',
    'src/stock_rsi/calendar.py', 'src/stock_rsi/time.py', 'src/stock_rsi/data.py')
INVENTORY = 'experiments/qlib/low-beta60-continuous-minute-source-inventory-summary.json'
OLD_PROOF = 'experiments/qlib/low-beta60-minute-source-verification.json'
RAW_PROOF = 'experiments/qlib/low-beta60-raw-extension-verification.json'


def authenticate_inputs(base, repo, path, expected_sha):
    base, repo, path = Path(base), Path(repo), Path(path)
    if file_sha(path) != expected_sha:
        raise ValueError('frozen2026minute plan changed')
    p = json.loads(path.read_text())
    if (p['status'] != 'FROZEN_LOW_BETA60_2026_MINUTE_EXTENSION_SOURCE'
            or type(p['max_fresh_query_reservations']) is not int or p['max_fresh_query_reservations'] != 247
            or p['max_attempts_per_request'] != 1 or p['stop_after_consecutive_source_failures'] != 3
            or p['inter_query_delay_seconds'] != .05 or p['host'] != '116.205.183.150:7709'
            or p['timeout_seconds'] != 3 or p['package_version'] != '3.2.3'
            or p['window'] != ['2026-01-01', '2026-10-13']
            or p['output_directory'] != 'low-beta60-minutes-2026-20261021'
            or set(p['method_code_sha256']) != set(METHOD_FILES)):
        raise ValueError('fixed247 source protocol changed')
    for field, parent in (('method_code_sha256', repo), ('public_evidence_sha256', repo), ('local_source_sha256', base)):
        for name, h in p[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(parent / name) != h:
                raise ValueError('frozen method/source/evidence changed')
    if not {INVENTORY, OLD_PROOF, RAW_PROOF, p['design_file']} <= set(p['public_evidence_sha256']):
        raise ValueError('fixed inventory and original source evidence required')
    inventory = json.loads((repo / INVENTORY).read_text())
    old_proof = json.loads((repo / OLD_PROOF).read_text())
    old = base / 'low-beta60-minutes-dev-20261021'
    if file_sha(old / 'manifest.json') != old_proof['capture_manifest_sha256']:
        raise ValueError('original1332minute manifest changed')
    old_manifest = json.loads((old / 'manifest.json').read_text())
    if len(old_manifest['per_session_sha256']) != 1332 or old_manifest['complete_capture'] is not True:
        raise ValueError('complete original source prefix required')
    for name, h in old_manifest['per_session_sha256'].items():
        if Path(name).name != name or file_sha(old / 'sessions' / name) != h:
            raise ValueError('original1332source bytes changed')
    old_results = json.loads((repo / 'experiments/qlib/low-beta60-minute-source-results.json').read_text())
    old_audit = json.loads((repo / 'experiments/qlib/low-beta60-minute-source-independent-audit.json').read_text())
    if (old_results['admitted_for_reconstructed_execution'] is not True
            or old_results['status_counts'] != {'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE': 1332}
            or file_sha(repo / 'experiments/qlib/low-beta60-minute-source-results.json') != old_proof['admission_summary_sha256']
            or file_sha(repo / 'experiments/qlib/low-beta60-minute-source-independent-audit.json') != old_proof['independent_audit_sha256']
            or old_audit['reconstructed_source_admission_passes'] is not True):
        raise ValueError('independently admitted old1332sources absent')
    raw = base / 'low-beta60-raw-extension-20261021'
    if file_sha(raw / 'manifest.json') != inventory['raw_manifest_sha256']:
        raise ValueError('same original raw source extension required')
    m = json.loads((raw / 'manifest.json').read_text())
    bars = {}
    for c, h in m['per_code_sha256'].items():
        f = raw / 'codes' / (c + '.json')
        if file_sha(f) != h:
            raise ValueError('raw source packet changed')
        bars[c] = {r['date']: r for r in json.loads(f.read_text())['bars']}
    target = base / 'low-beta60-calendar-extension-formations-20261021/targets.json'
    if file_sha(target) != inventory['target_sha256']:
        raise ValueError('same unchanged34month targets required')
    targets = json.loads(target.read_text())['low_beta60']
    seen, required = set(), []
    for day, t in sorted(targets.items()):
        seen.update(t['weights'])
        if day < '2026-01-01':
            continue
        for code in sorted(seen):
            if bars[code][day]['tradestatus'] == '1':
                required.append([code, day])
    reused, fresh = inventory['reused2026_session_provenance'], inventory['uncached2026_requests']
    if (required != inventory['required2026_requests'] or len(required) != 754 or len(reused) != 507 or len(fresh) != 247
            or set(reused) | {c + '-' + d + '.json' for c, d in fresh} != {c + '-' + d + '.json' for c, d in required}
            or inventory['rejected_cached_pairs'] or inventory['cross_cache_signature_conflicts']):
        raise ValueError('complete754potential source requirement or507/247 partition changed')
    for root, h in inventory['source_manifest_sha256'].items():
        if Path(root).name != root or file_sha(base / root / 'manifest.json') != h:
            raise ValueError('cached original source manifest changed')
    for name, origin in reused.items():
        if Path(name).name != name or Path(origin['root']).name != origin['root']:
            raise ValueError('safe reused source path required')
        code, day = name[:-5].split('-', 1)
        f = base / origin['root'] / 'sessions' / name
        if file_sha(f) != origin['sha256']:
            raise ValueError('reused source bytes changed')
        inspect_packet(code, day, json.loads(f.read_text()), bars[code][day])
    return p, reused, fresh, bars


def main(argv=None):
    parser = argparse.ArgumentParser()
    for n in ('source-root', 'plan', 'expected-plan-sha256', 'output-dir'):
        parser.add_argument('--' + n, required=True)
    a = parser.parse_args(argv)
    base, repo, out = Path(a.source_root), Path(__file__).resolve().parents[1], Path(a.output_dir)
    if out.exists():
        raise ValueError('preserve existing source attempt; no automatic resume')
    p, reused, fresh, _ = authenticate_inputs(base, repo, a.plan, a.expected_plan_sha256)
    if out.resolve() != (base / p['output_directory']).resolve() or version('eltdx') != p['package_version']:
        raise ValueError('fixed output or installed SDK changed')
    clients = []
    def fetch(code, day):
        from eltdx import TdxClient, to_jsonable
        if not clients:
            client = TdxClient(host=p['host'], timeout=3, heartbeat_interval=None, probe_hosts=False,
                               pool_size=1, server_count=1, connections_per_server=1)
            try:
                client.__enter__()
            except BaseException:
                client.close()
                raise
            clients.append(client)
        return to_jsonable(clients[0].minutes.history(code.lower(), day, include_raw=True))
    try:
        m = capture_extension(base, out, reused, fresh, p, fetch, plan_bytes=Path(a.plan).read_bytes())
    finally:
        for client in clients:
            client.close()
    print('2026 minute source capture', m['captured'], '/', m['requested'], m['response_status_counts'], flush=True)
    return 0 if m['complete_capture'] and m['response_status_counts'] == {'RESPONSE_CAPTURED': 754} else 2


if __name__ == '__main__':
    raise SystemExit(main())
