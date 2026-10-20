"""Frozen calendar-only beta60 extension: formations, never portfolio ROI."""
import argparse
import json
from pathlib import Path

from scripts.prepare_low_beta60_pre2026 import METHOD_FILES as ORIGINAL_FILES
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_cninfo_orj_signal_pre2026 import price_input_digest
from scripts.run_qlib_low_risk_pre2026 import input_hashes, parse_memberships
from stock_rsi.low_beta60_extension import extend_targets, json_bytes
from stock_rsi.qlib_snapshot import QlibSnapshot

METHOD_FILES = (*ORIGINAL_FILES, 'src/stock_rsi/low_beta60_extension.py',
                'scripts/prepare_low_beta60_extension.py')
START, END = '2024-01-02', '2026-10-13'
CONFIRMATION = 'experiments/qlib/low-beta60-intraday-development-verification.json'


def extension_input_hashes(provider, memberships, end):
    """Bind all names eligible during the extension, including 2026-only members."""
    provider = Path(provider)
    codes = sorted(c for c, spans in memberships.items()
                   if any(a <= end and b >= '2023-12-29' for a, b in spans))
    return {'price_files': price_input_digest(provider, codes),
            **{name: sha256_file(provider / name) for name in (
                'calendars/day.txt', 'instruments/csi500.txt', 'features/sh000905/close.day.bin')}}


def bound_path(parent, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('safe relative source path required')
    return parent / relative


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('request', 'sha256', 'source-root', 'provider-uri', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    source, provider, out = Path(args.source_root), Path(args.provider_uri), Path(args.output_dir)
    if out.exists():
        raise ValueError('preserve previous formation attempt')
    if sha256_file(args.request) != args.sha256:
        raise ValueError('frozen formation request changed')
    request = json.loads(Path(args.request).read_text())
    if (request['status'] != 'FROZEN_LOW_BETA60_CALENDAR_EXTENSION_FORMATIONS_ONLY'
            or request['window'] != [START, END] or request['candidate_budget'] != 1
            or request['selected_family'] != 'low_beta60' or request['expected_formations'] != 34
            or request['portfolio_returns_allowed'] is not False or request['sealed_evidence'] is not False
            or set(request['method_code_sha256']) != set(METHOD_FILES)):
        raise ValueError('calendar-only single-method protocol changed')
    for field, parent in (('method_code_sha256', repo), ('public_evidence_sha256', repo),
                          ('local_source_sha256', source)):
        for name, expected in request[field].items():
            if sha256_file(bound_path(parent, name)) != expected:
                raise ValueError('frozen method or reference evidence changed')
    if CONFIRMATION not in request['public_evidence_sha256']:
        raise ValueError('prior independent intraday confirmation binding required')
    confirmation = json.loads((repo / CONFIRMATION).read_text())
    if (confirmation['all6profiles_valid'] is not True
            or confirmation['all3_extra40_reference_development_conditions_pass'] is not True
            or confirmation['all42_account_files_and_all6profile_metadata_byte_identical'] is not True):
        raise ValueError('pre2026 intraday account confirmation absent')
    reference_files = [request[k] for k in ('reference_targets_file', 'reference_receipts_file')]
    if any(n not in request['local_source_sha256'] for n in reference_files):
        raise ValueError('frozen reference target and receipt bindings required')
    members = parse_memberships((provider / 'instruments/csi500.txt').read_text())
    if (input_hashes(provider, members) != request['pre2026_input_sha256']
            or extension_input_hashes(provider, members, END) != request['extension_input_sha256']):
        raise ValueError('frozen input snapshot changed')
    snapshot = QlibSnapshot(provider)
    if snapshot.calendar[-1].isoformat() != END:
        raise ValueError('explicit partial-October source cap changed')
    reference_targets, reference_receipts = [bound_path(source, n).read_bytes() for n in reference_files]
    targets, receipts = extend_targets(snapshot, members, reference_targets, reference_receipts,
                                       end=END, permitted_end=END)
    if (len(receipts) != 34
            or any(r['latest_factor_price_read'] != r['formation_asof'] for r in receipts)):
        raise ValueError('complete bounded monthly formations required')
    out.mkdir(parents=True)
    for name, data in (('targets.json', json_bytes(targets)), ('formation_receipts.json', json_bytes(receipts)),
                       ('pre2026_targets.json', reference_targets),
                       ('pre2026_formation_receipts.json', reference_receipts)):
        with (out / name).open('xb') as stream:
            stream.write(data)
    summary = {
        'status': 'LOW_BETA60_CALENDAR_EXTENSION_FORMATIONS_ONLY_NO_PORTFOLIO_ROI',
        'request_sha256': args.sha256, 'method_code_sha256': request['method_code_sha256'],
        'input_sha256': request['extension_input_sha256'], 'formations': len(receipts),
        'extension_formations': sum(r['execution_session'] > '2025-12-31' for r in receipts),
        'window': [START, END], 'candidate_budget': 1, 'selected_family': 'low_beta60',
        'pre2026_target_and_receipt_bytes_identical': True,
        'prefix_checked_before_any_additional_formation_query': True,
        'eligible_range': [min(r['eligible'] for r in receipts), max(r['eligible'] for r in receipts)],
        'latest_formation_price_read': max(r['latest_factor_price_read'] for r in receipts),
        'artifact_sha256': {p.name: sha256_file(p) for p in sorted(out.iterdir())},
        'network_queries': 0, 'portfolio_returns_computed': False,
        '2026_factor_values_queried': True, '2026_execution_returns_queried': False,
        'requested_full_october_complete': False, 'sealed_evidence': False,
        'historical_arrival_verified': False, 'objective_achieved': False,
        'evidence_level': 'REAL_PRICE_ENGINEERING_ONLY_NOT_OS_FUTURE_ISOLATED',
    }
    with (out / 'summary.json').open('xb') as stream:
        stream.write(json_bytes(summary))
    print('lowbeta60 bounded formations', len(receipts), 'original24 prefix exact; no portfolio ROI', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
