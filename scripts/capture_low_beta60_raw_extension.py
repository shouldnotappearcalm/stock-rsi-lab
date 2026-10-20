"""One bounded foreground source attempt for unchanged beta60 targets."""
import argparse
import json
import socket
from importlib.metadata import version
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, source_code
from scripts.capture_illiquidity_raw_development import read_vendor_response
from scripts.low_beta60_extension_sources import START, END, assemble_packet, capture_packets

METHOD_FILES = ('scripts/capture_low_beta60_raw_extension.py', 'scripts/low_beta60_extension_sources.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py', 'scripts/capture_low_risk_raw_account_data.py',
    'scripts/capture_illiquidity_raw_development.py', 'scripts/fundamental_query_journal.py',
    'scripts/inventory_low_beta60_sources.py', 'scripts/capture_frozen_target_development_data.py')
INVENTORY = 'experiments/qlib/low-beta60-calendar-extension-raw-inventory.json'
CONFIRMATION = 'experiments/qlib/low-beta60-calendar-extension-verification.json'
SOURCES = ('low-risk-raw-account-data-20261017', 'szse-value-raw-full-20261017', 'reversal-raw-full-20261017')


def relative(parent, name):
    if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('safe relative frozen source path required')
    return parent / name


def authenticate_request(path, expected_sha, repo, base):
    if sha256_file(path) != expected_sha:
        raise ValueError('frozen raw extension request changed')
    r = json.loads(Path(path).read_text())
    if (r['status'] != 'FROZEN_LOW_BETA60_RAW_EXTENSION_SOURCE_REQUEST' or r['window'] != [START, END]
            or r['maximum_source_reservations'] != 76 or r['max_attempts_per_query'] != 1
            or r['maximum_consecutive_failed_codes'] != 3 or r['maximum_administrative_login_attempts'] != 1
            or r['socket_timeout_seconds'] != 20 or r['output_directory'] != 'low-beta60-raw-extension-20261021'
            or set(r['method_code_sha256']) != set(METHOD_FILES)):
        raise ValueError('bounded raw extension protocol changed')
    for name, expected in r['method_code_sha256'].items():
        if sha256_file(relative(repo, name)) != expected:
            raise ValueError('source method changed')
    for field, root in (('public_evidence_sha256', repo), ('local_source_sha256', base)):
        for name, expected in r[field].items():
            if sha256_file(relative(root, name)) != expected:
                raise ValueError('frozen source or evidence bytes changed')
    if not {INVENTORY, CONFIRMATION, r['design_file']} <= set(r['public_evidence_sha256']):
        raise ValueError('source inventory and formation confirmation bindings required')
    inventory = json.loads((repo / INVENTORY).read_text())
    confirmation = json.loads((repo / CONFIRMATION).read_text())
    if (confirmation['all34formations_independently_reconstructed'] is not True
            or confirmation['old24target_and_receipt_bytes_identical'] is not True
            or inventory['cross_cache_raw_core_conflict_codes'] or inventory['original_pre2026_prefix_conflict_codes']
            or inventory['source_priority_fixed_before_inventory'] != list(SOURCES)):
        raise ValueError('unchanged target formation or source agreement absent')
    target_path = base / 'low-beta60-calendar-extension-formations-20261021/targets.json'
    if sha256_file(target_path) != r['target_sha256'] or r['target_sha256'] != inventory['target_sha256']:
        raise ValueError('fixed target file changed')
    targets = json.loads(target_path.read_text())['low_beta60']
    codes = sorted({c for t in targets.values() for c in t['weights']})
    if codes != r['codes'] or len(codes) != 79 or len(targets) != 34:
        raise ValueError('full unchanged79name34formation schedule required')
    for c in codes:
        source_code(c)
    calendar_path = base / 'low-risk-raw-account-data-20261017/calendar.json'
    if sha256_file(calendar_path) != inventory['source_calendar_sha256'][SOURCES[0]]:
        raise ValueError('explicit exchange calendar changed')
    sessions = [d for d in json.loads(calendar_path.read_text())['sessions'] if START <= d <= END]
    if sessions != sorted(set(sessions)) or len(sessions) != 671 or sessions[0] != START or sessions[-1] != END:
        raise ValueError('complete671session calendar required')
    olddir = base / 'low-beta60-raw-dev-20261021'
    if sha256_file(olddir / 'manifest.json') != inventory['original_pre2026_raw_manifest_sha256']:
        raise ValueError('original raw prefix manifest changed')
    old = json.loads((olddir / 'manifest.json').read_text())
    if old['per_code_sha256'] != r['original_packet_sha256'] or len(old['per_code_sha256']) != 69:
        raise ValueError('original69packet identities required')
    originals = {}
    for code, expected in old['per_code_sha256'].items():
        p = olddir / 'codes' / (code + '.json')
        if sha256_file(p) != expected:
            raise ValueError('original packet bytes changed')
        originals[code] = json.loads(p.read_text())
    routes, cached = {}, {}
    for code in codes:
        item = inventory['items'][code]
        name = item['priority_route']
        if name is None:
            continue
        if name not in SOURCES or sha256_file(base / name / 'manifest.json') != inventory['source_manifest_sha256'][name]:
            raise ValueError('fixed cache source manifest changed')
        expected = next(c['original_packet_sha256'] for c in item['choices'] if c['source_directory'] == name)
        path = base / name / 'codes' / (code + '.json')
        if sha256_file(path) != expected:
            raise ValueError('cached source bytes changed')
        packet = json.loads(path.read_text())
        assemble_packet(code, packet, originals.get(code), sessions)
        cached[code] = packet
        routes[code] = {'source_directory': name, 'packet_sha256': expected}
    fresh = [c for c in codes if c not in routes]
    if (routes != r['reuse_routes'] or fresh != r['fresh_codes'] or len(routes) != 55 or len(fresh) != 24
            or sum(3 if c in originals else 5 for c in fresh) != 76):
        raise ValueError('source routing or76query budget changed')
    return r, codes, sessions, originals, cached


class SourceSession:
    def __init__(self, out, request_sha, sdk):
        self.out, self.request_sha, self.sdk = Path(out), request_sha, sdk
        self.attempted = False
        self.error = None

    def __call__(self, code, component, parameters):
        if self.error is not None:
            raise RuntimeError('administrative login already failed; no retry')
        if not self.attempted:
            self.attempted = True
            atomic_json(self.out / 'login-reserved-1.json', {'attempt': 1, 'request_sha256': self.request_sha})
            record = {}
            try:
                login = self.sdk.login()
                record = {'error_code': login.error_code, 'error_msg': login.error_msg}
                if login.error_code != '0':
                    raise RuntimeError('source administrative login failed: ' + login.error_msg)
            except Exception as exc:
                self.error = type(exc).__name__
                atomic_json(self.out / 'login-response-1.json', {**record, 'error_type': type(exc).__name__, 'error': str(exc)})
                raise
            atomic_json(self.out / 'login-response-1.json', record)
        symbol = source_code(code)
        if component == 'daily':
            response = self.sdk.query_history_k_data_plus(symbol, ','.join(BAR_FIELDS), **parameters)
        elif component.startswith('dividend'):
            response = self.sdk.query_dividend_data(symbol, **parameters)
        else:
            response = self.sdk.query_adjust_factor(symbol, **parameters)
        return read_vendor_response(response)

    def close(self):
        if self.attempted:
            try:
                result = self.sdk.logout()
                record = {'error_code': getattr(result, 'error_code', None), 'error_msg': getattr(result, 'error_msg', None)}
            except Exception as exc:
                record = {'error_type': type(exc).__name__, 'error': str(exc)}
            atomic_json(self.out / 'logout-response.json', record)


def main(argv=None):
    p = argparse.ArgumentParser()
    for n in ('request', 'expected-request-sha256', 'source-root', 'output-dir'):
        p.add_argument('--' + n, required=True)
    a = p.parse_args(argv)
    base, repo, out = Path(a.source_root), Path(__file__).resolve().parents[1], Path(a.output_dir)
    if out.exists():
        raise ValueError('preserve existing source attempt; no automatic resume')
    r, codes, sessions, originals, cached = authenticate_request(a.request, a.expected_request_sha256, repo, base)
    if out.resolve() != (base / r['output_directory']).resolve() or version('baostock') != r['baostock_version']:
        raise ValueError('fixed output or installed provider version changed')
    import baostock as bs
    socket.setdefaulttimeout(20)
    session = SourceSession(out, a.expected_request_sha256, bs)
    try:
        manifest = capture_packets(out, codes, sessions, originals, cached, a.expected_request_sha256, session,
                                   request_bytes=Path(a.request).read_bytes())
    finally:
        session.close()
    manifest.update(method_code_sha256=r['method_code_sha256'], target_sha256=r['target_sha256'],
        original_packet_sha256=r['original_packet_sha256'], reuse_routes=r['reuse_routes'],
        source_manifest_sha256=r['source_manifest_sha256'], SDK_decoded_responses_not_TCP_wire=True,
        source_units={'price': 'CNY/share', 'volume': 'shares', 'amount': 'CNY'},
        original_source_files_changed=False, raw_full_October_complete=False)
    atomic_json(out / 'manifest.json', manifest)
    print('raw extension complete', manifest['names'], '/', len(codes), 'errors', len(manifest['errors_sha256']), flush=True)
    return 0 if manifest['names'] == len(codes) else 2


if __name__ == '__main__':
    raise SystemExit(main())
