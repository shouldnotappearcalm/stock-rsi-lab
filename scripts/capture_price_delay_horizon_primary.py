"""Capture one fixed missing-action notice; no account or inferred economics."""
import argparse
import json
from pathlib import Path

from scripts.capture_budgeted_corporate_notices_pre2026 import journaled_bytes, read_wire
from scripts.fundamental_query_journal import QueryJournal, file_sha, write_packet_once

OUTPUT = 'price-delay-horizon-missing-primary-20261021'
METHODS = ('scripts/capture_price_delay_horizon_primary.py',
    'scripts/capture_budgeted_corporate_notices_pre2026.py',
    'scripts/fundamental_query_journal.py', 'scripts/audit_cninfo_report_admission.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py')
PROTOCOL = 'docs/research/price-delay-horizon-single-primary-plan-2026-10-21.md'
LOCAL = ('price-delay-raw-horizon-20261021/manifest.json',
    'price-delay-raw-horizon-20261021/price-delay-scope.json',
    'price-delay-raw-horizon-20261021/errors/SH603233.json')
PROFILE = {'status': 'FROZEN_PRICE_DELAY_ONE_MISSING_ACTION_PRIMARY',
    'instrument': 'SH603233', 'publication_day': '2026-10-12',
    'url': 'https://static.cninfo.com.cn/finalpage/2026-10-12/1225600412.PDF',
    'maximum_http_queries': 1, 'max_attempts': 1, 'output_directory': OUTPUT,
    'protocol_file': PROTOCOL,
    'portfolio_returns_to_compute': False, 'investment_rules_changed': False}


def read(p):
    return json.loads(Path(p).read_bytes())


def authenticate(path, expected, repo, base):
    if file_sha(path) != expected:
        raise ValueError('frozen primary request SHA changed')
    r = read(path)
    if (any(type(r.get(k)) is not type(v) or r[k] != v for k, v in PROFILE.items())
            or set(r['method_code_sha256']) != set(METHODS)
            or set(r['local_source_sha256']) != set(LOCAL)):
        raise ValueError('one exact primary identity and source-error bindings required')
    if file_sha(repo / PROTOCOL) != r['protocol_sha256']:
        raise ValueError('frozen primary protocol changed')
    for field, root in (('method_code_sha256', repo), ('local_source_sha256', base)):
        for name, h in r[field].items():
            if file_sha(root / name) != h:
                raise ValueError('frozen primary method/source changed')
    return r


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ('request', 'expected-request-sha256', 'source-root', 'output-dir'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--preflight-only', action='store_true')
    a = p.parse_args(argv)
    repo, base, out = Path(__file__).resolve().parents[1], Path(a.source_root), Path(a.output_dir)
    if out.exists():
        raise ValueError('preserve existing primary capture; no resume or retry')
    r = authenticate(a.request, a.expected_request_sha256, repo, base)
    if out.resolve() != (base / OUTPUT).resolve():
        raise ValueError('fixed primary output required')
    if a.preflight_only:
        print('one exact primary PDF; no output or HTTP', flush=True)
        return 0
    out.mkdir(parents=True)
    (out / 'request.json').write_bytes(Path(a.request).read_bytes())
    docs, errors, checked = {}, {}, False
    try:
        data, receipt = journaled_bytes(QueryJournal(out, max_queries=1, max_attempts=1),
            {'source': 'CNINFO_HTTP', 'url': r['url'], 'payload': None,
             'request_sha256': a.expected_request_sha256}, lambda: read_wire(r['url'], None))
        if not data.startswith(b'%PDF'):
            raise ValueError('original complete PDF response required')
        pdf = out / 'SH603233.pdf'
        with pdf.open('xb') as f:
            f.write(data)
        docs['SH603233'] = {k: r[k] for k in ('instrument', 'publication_day', 'url')}
        docs['SH603233'].update(file=pdf.name, sha256=file_sha(pdf), pdf_receipt=receipt)
    except Exception as exc:
        errors['SH603233'] = {'error_type': type(exc).__name__, 'error': str(exc)}
    finally:
        try:
            authenticate(a.request, a.expected_request_sha256, repo, base)
        except Exception as exc:
            errors['postcheck'] = {'error_type': type(exc).__name__, 'error': str(exc)}
        else:
            checked = True
        complete = len(docs) == 1 and not errors and checked
        write_packet_once(out / 'manifest.json', {'status': 'PRICE_DELAY_ONE_PRIMARY_CAPTURE_RECORDED',
            'request_sha256': a.expected_request_sha256, 'documents': docs, 'errors': errors,
            'http_query_reservations': len(list(out.rglob('reserved-*.json'))),
            'source_inputs_unchanged_after_capture': checked, 'capture_complete': complete,
            'documents_financially_reviewed': False, 'source_admitted_for_account_replay': False,
            'historical_arrival_verified': False, 'portfolio_returns_computed': False,
            'investment_rules_changed': False, 'objective_achieved': False})
    print('single primary capture complete', complete, 'no financial/account admission', flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
