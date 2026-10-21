"""Four exact corporate-source questions, using the existing HTTP collector."""
import argparse
import json
import time
from pathlib import Path

from scripts.capture_low_beta60_corporate_2026 import capture_documents, METHOD_FILES as BASE_METHODS
from scripts.capture_budgeted_corporate_notices_pre2026 import read_wire
from scripts.fundamental_query_journal import file_sha, write_packet_once

OUTPUT = 'price-delay-horizon-remaining-primary-20261021'
PROTOCOL = 'docs/research/price-delay-horizon-four-primary-plan-2026-10-21.md'
METHODS = (*BASE_METHODS, 'scripts/capture_price_delay_horizon_remaining_primary.py')
LOCAL = ('price-delay-raw-horizon-v2-20261021/manifest.json',
    'price-delay-horizon-corporate-inventory-20261021.json')
PUBLIC = ('experiments/qlib/price-delay-horizon-local-reassembly-independent-audit.json', PROTOCOL)
DOCUMENTS = tuple({'document_id': code + '-' + day.replace('-', ''), 'instrument': code,
    'publication_day': day, 'url': 'https://static.cninfo.com.cn/finalpage/' + day + '/' + identity + '.PDF'}
    for code, day, identity in (('SH603605', '2026-10-12', '1225600426'),
        ('SH603596', '2026-04-30', '1225259935'), ('SH603606', '2026-05-19', '1225313998'),
        ('SZ002831', '2026-05-29', '1225335706')))
PROFILE = {'status': 'FROZEN_PRICE_DELAY_FOUR_REMAINING_PRIMARY_SOURCE_QUESTIONS',
    'maximum_http_queries': 4, 'max_attempts_per_identity': 1, 'minimum_interval_seconds': 0.3,
    'output_directory': OUTPUT, 'documents': list(DOCUMENTS),
    'investment_rules_changed': False, 'portfolio_returns_to_compute': False}


def read(p):
    return json.loads(Path(p).read_bytes())


def authenticate(path, expected, repo, base):
    if file_sha(path) != expected:
        raise ValueError('four-primary frozen request changed')
    r = read(path)
    if (any(type(r.get(k)) is not type(v) or r[k] != v for k, v in PROFILE.items())
            or set(r['method_code_sha256']) != set(METHODS)
            or set(r['local_source_sha256']) != set(LOCAL)
            or set(r['public_evidence_sha256']) != set(PUBLIC)):
        raise ValueError('four exact single-attempt originals required')
    for field, root in (('method_code_sha256', repo), ('local_source_sha256', base),
                        ('public_evidence_sha256', repo)):
        for name, h in r[field].items():
            if file_sha(root / name) != h:
                raise ValueError('frozen primary code/source/evidence changed')
    return r


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ('request', 'expected-request-sha256', 'source-root', 'output-dir'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--preflight-only', action='store_true')
    a = p.parse_args(argv)
    repo, base, out = Path(__file__).resolve().parents[1], Path(a.source_root), Path(a.output_dir)
    if out.exists() or out.resolve() != (base / OUTPUT).resolve():
        raise ValueError('fixed unused primary output required; preserve previous capture')
    r = authenticate(a.request, a.expected_request_sha256, repo, base)
    if a.preflight_only:
        print('four exact primary documents;no output/HTTP/account', flush=True)
        return 0
    next_request = 0.
    def fetch(url, payload):
        nonlocal next_request
        pause = next_request - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        try:
            return read_wire(url, payload)
        finally:
            next_request = time.monotonic() + 0.3
    complete = False
    try:
        result = capture_documents(r, base, out, fetch, request_sha=a.expected_request_sha256)
    finally:
        if out.exists():
            postcheck = {'frozen_inputs_unchanged': False}
            try:
                authenticate(a.request, a.expected_request_sha256, repo, base)
            except Exception as exc:
                postcheck.update(error_type=type(exc).__name__, error=str(exc))
            else:
                postcheck['frozen_inputs_unchanged'] = True
            if (out / 'manifest.json').exists():
                m = read(out / 'manifest.json')
                complete = (m['capture_complete'] is True and not m['errors'] and not m['pending_documents']
                    and m['http_query_reservations'] == 4 and postcheck['frozen_inputs_unchanged'] is True)
                write_packet_once(out / 'price-delay-scope.json', {'request_sha256': a.expected_request_sha256,
                    'source_manifest_sha256': file_sha(out / 'manifest.json'), 'postcheck': postcheck,
                    'capture_complete': complete, 'documents_financially_reviewed': False,
                    'source_admitted_for_account_replay': False, 'portfolio_returns_computed': False,
                    'investment_rules_changed': False, 'objective_achieved': False})
    print('four-primary capture complete', complete, 'financial/account admission separate', flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
