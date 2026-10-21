"""Authenticate the fixed source inventory before any Oct20 extension query."""
import argparse
import json
import socket
from importlib.metadata import version
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file
from scripts.capture_illiquidity_raw_development import read_vendor_response
from scripts.capture_low_beta60_raw_extension import SourceSession, relative
from scripts.inventory_low_beta60_sources import core_fingerprint
from scripts.low_beta60_horizon_sources import START, OLD_END, END, capture_horizon, load_dividend_reuse, _preflight

INVENTORY = 'experiments/qlib/low-beta60-post-oct13-source-inventory.json'
PRIOR_PLAN = 'experiments/qlib/low-beta60-raw-extension-source-request-v2.json'
TARGET = 'low-beta60-calendar-extension-formations-20261021/targets.json'
OLD_DIR = 'low-beta60-raw-extension-20261021'
OUTPUT = 'low-beta60-raw-horizon-20261021'
METHOD_FILES = ('scripts/capture_low_beta60_horizon_sources.py', 'scripts/low_beta60_horizon_sources.py',
    'scripts/capture_low_beta60_raw_extension.py', 'scripts/capture_cninfo_csi500_reports_pre2026.py',
    'scripts/capture_illiquidity_raw_development.py', 'scripts/capture_low_risk_raw_account_data.py',
    'scripts/fundamental_query_journal.py', 'scripts/inventory_low_beta60_sources.py',
    'scripts/capture_frozen_target_development_data.py')


def authenticate_request(path, expected_sha, repo, base):
    if sha256_file(path) != expected_sha:
        raise ValueError('external frozen horizon request checksum changed')
    r = json.loads(Path(path).read_text())
    if (r['status'] != 'FROZEN_LOW_BETA60_OCT20_SOURCE_CAPTURE_NO_ROI' or r['window'] != [START, END]
            or r['unconditional_interim_observation_end'] != END or r['full_October_complete'] is not False
            or type(r['maximum_source_reservations']) is not int or r['maximum_source_reservations'] != 214
            or r['max_attempts_per_query'] != 1 or r['maximum_consecutive_failed_codes'] != 3
            or r['maximum_administrative_login_attempts'] != 1 or r['socket_timeout_seconds'] != 20
            or r['output_directory'] != OUTPUT or r['portfolio_returns_to_compute'] is not False
            or r['investment_rule_changes_allowed'] is not False or set(r['method_code_sha256']) != set(METHOD_FILES)):
        raise ValueError('bounded source horizon protocol changed')
    for key, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo), ('local_source_sha256', base)):
        for name, expected in r[key].items():
            if sha256_file(relative(root, name)) != expected:
                raise ValueError('frozen method/source/evidence bytes changed: ' + name)
    if not {INVENTORY, PRIOR_PLAN, r['design_file'], 'experiments/qlib/low-beta60-extension-event-plan.json'} <= set(r['public_evidence_sha256']):
        raise ValueError('inventory, prior request and unconditional cutoff bindings required')
    cutoff = json.loads((repo / 'experiments/qlib/low-beta60-extension-event-plan.json').read_text())
    if cutoff['unconditional_interim_observation_end'] != END:
        raise ValueError('prior unconditional cutoff changed')
    inventory = json.loads((repo / INVENTORY).read_text())
    oldplan = json.loads((repo / PRIOR_PLAN).read_text())
    oldmanifest = json.loads((base / OLD_DIR / 'manifest.json').read_text())
    if (sha256_file(base / OLD_DIR / 'manifest.json') != inventory['original_manifest_sha256']
            or oldmanifest['per_code_sha256'] != r['original_packet_sha256'] or inventory['conflicts']
            or len(oldmanifest['per_code_sha256']) != 79 or inventory['unconditional_interim_observation_end'] != END):
        raise ValueError('original79 source manifest or cache agreement changed')
    targets = json.loads((base / TARGET).read_text())['low_beta60']
    codes = sorted({c for t in targets.values() for c in t['weights']})
    if (codes != r['codes'] or codes != sorted(oldmanifest['per_code_sha256']) or len(targets) != 34
            or sha256_file(base / TARGET) != oldplan['target_sha256'] or oldplan['target_sha256'] != r['target_sha256']):
        raise ValueError('unchanged34 formation79 name schedule required')
    sessions = json.loads((base / OLD_DIR / 'calendar.json').read_text())['sessions']
    if len(sessions) != 671 or sessions[0] != START or sessions[-1] != OLD_END:
        raise ValueError('original671 session calendar changed')
    originals, tails, routes = {}, {}, {}
    for code in codes:
        p = base / OLD_DIR / 'codes' / (code + '.json')
        if sha256_file(p) != oldmanifest['per_code_sha256'][code]:
            raise ValueError('original packet bytes changed')
        old = json.loads(p.read_text()); originals[code] = old
        item = inventory['items'][code]
        if item['original_packet_sha256'] != sha256_file(p):
            raise ValueError('inventory original packet identity changed')
        choice = item['priority_route']
        if choice is None:
            continue
        name = choice['source_directory']
        if (name not in inventory['source_priority']
                or sha256_file(base / name / 'manifest.json') != inventory['source_manifest_sha256'][name]
                or sha256_file(base / name / 'calendar.json') != inventory['source_calendar_sha256'][name]):
            raise ValueError('cached source manifest/calendar changed')
        p = base / name / 'codes' / (code + '.json')
        if sha256_file(p) != choice['packet_sha256']:
            raise ValueError('cached tail packet bytes changed')
        packet = json.loads(p.read_text())
        cache_sessions = json.loads((base / name / 'calendar.json').read_text())['sessions']
        if ([d for d in cache_sessions if START <= d <= OLD_END] != sessions
                or [d for d in cache_sessions if OLD_END < d <= '2026-10-16'] != choice['tail_dates']
                or packet['instrument'] != code or packet['window'] != [START, '2026-10-16']):
            raise ValueError('cached source calendar or packet window changed')
        if core_fingerprint({'bars': [b for b in packet['bars'] if b['date'] <= OLD_END]}) != core_fingerprint(old):
            raise ValueError('cached old market prefix disagrees')
        for key in ('distributions', 'adjustments'):
            prefix = [v for v in packet[key] if v['dividOperateDate'] <= OLD_END]
            if prefix != old[key]:
                raise ValueError('cached old corporate prefix disagrees')
        tails[code] = {key: [v for v in packet[key] if v[field] > OLD_END]
                       for key, field in (('bars', 'date'), ('distributions', 'dividOperateDate'), ('adjustments', 'dividOperateDate'))}
        if core_fingerprint({'bars': tails[code]['bars']}) != choice['tail_core_sha256']:
            raise ValueError('cached tail core changed')
        routes[code] = choice
    old_request_sha = sha256_file(repo / PRIOR_PLAN)
    reused = {code: load_dividend_reuse(base / OLD_DIR, originals[code], old_request_sha) for code in oldmanifest['fresh_codes']}
    if (len(tails) != 55 or len(reused) != 24 or set(tails) & set(reused) or set(tails) | set(reused) != set(codes)
            or routes != r['reuse_tail_routes'] or sorted(reused) != r['reuse_dividend_codes']):
        raise ValueError('exact55tail24annual reuse routing required')
    _preflight(originals, tails, reused, sessions)
    return r, originals, tails, reused, sessions


class HorizonSession(SourceSession):
    def __call__(self, code, component, parameters):
        if component != 'calendar':
            return super().__call__(code, component, parameters)
        if code != 'CN_STOCK_CALENDAR' or parameters != {'start_date': '2026-10-14', 'end_date': END}:
            raise ValueError('fixed source calendar request required')
        if self.error is not None:
            raise RuntimeError('administrative login already failed; no retry')
        if not self.attempted:
            self.attempted = True
            atomic_json(self.out / 'login-reserved-1.json', {'attempt': 1, 'request_sha256': self.request_sha})
            record = {}
            try:
                response = self.sdk.login()
                record = {'error_code': response.error_code, 'error_msg': response.error_msg}
                if response.error_code != '0':
                    raise RuntimeError('source administrative login failed: ' + response.error_msg)
            except Exception as exc:
                self.error = type(exc).__name__
                atomic_json(self.out / 'login-response-1.json', {**record, 'error_type': type(exc).__name__, 'error': str(exc)})
                raise
            atomic_json(self.out / 'login-response-1.json', record)
        return read_vendor_response(self.sdk.query_trade_dates(**parameters))


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ('request', 'expected-request-sha256', 'source-root', 'output-dir'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args(argv)
    base, out, repo = Path(a.source_root), Path(a.output_dir), Path(__file__).resolve().parents[1]
    if out.exists():
        raise ValueError('preserve existing attempt; no automatic resume')
    r, originals, tails, reused, sessions = authenticate_request(a.request, a.expected_request_sha256, repo, base)
    if out.resolve() != (base / OUTPUT).resolve() or version('baostock') != r['baostock_version']:
        raise ValueError('fixed output or source provider version changed')
    import baostock as bs
    socket.setdefaulttimeout(20)
    session = HorizonSession(out, a.expected_request_sha256, bs)
    try:
        manifest = capture_horizon(out, originals, tails, reused, sessions, session,
            request_bytes=Path(a.request).read_bytes(), maximum_queries=r['maximum_source_reservations'])
    finally:
        session.close()
        if (out / 'manifest.json').exists():
            manifest = json.loads((out / 'manifest.json').read_text())
            manifest.update(method_code_sha256=r['method_code_sha256'], target_sha256=r['target_sha256'],
                original_manifest_sha256=sha256_file(base / OLD_DIR / 'manifest.json'),
                SDK_decoded_responses_not_TCP_wire=True, original_source_files_changed=False,
                administrative_receipts_sha256={name: sha256_file(out / name) for name in
                    ('login-reserved-1.json', 'login-response-1.json', 'logout-response.json') if (out / name).exists()})
            atomic_json(out / 'manifest.json', manifest)
    print('horizon complete', manifest['capture_complete'], 'names', manifest['names'], 'queries', manifest['query_reservations_consumed'], flush=True)
    return 0 if manifest['capture_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
