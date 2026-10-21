"""Frozen source-only scenario builder; original240 admission stays false.

No account, portfolio score, network or mixed-year Parquet reader is called.
The separate cent-grid/encoding/clock premises are engineering assumptions.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime
import json
from pathlib import Path

from scripts.admit_illiquidity_minutes_pre2026 import METHOD_FILES as OLD_METHODS
from scripts.fundamental_query_journal import file_sha
from scripts.illiquidity_minute_sources import prefix_minute_requirements
from scripts.prepare_illiquidity_account_events import authenticate_sources, classify_source_coverage
from scripts.run_low_risk_intraday_replay import TapeBank
from scripts.run_low_risk_raw_share_validation import clean
from stock_rsi.archive_cent_clock import CONTRACT, archive_scenario_windows
from stock_rsi.archive_minute_probe import need
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler import compile_distribution_events

RAW = 'illiquidity-raw-source-continuation-20261020'
PROOF = 'illiquidity-corporate-reviewed-20261020'
TARGET = 'illiquidity-development-targets-20261020.json'
EVENTS = 'illiquidity-source-events-20261020'
OLD = 'tdx-fixed-order-history-20261017'
EXTRA = 'illiquidity-minutes-dev-20261021'
ARCHIVE = 'illiquidity-hf-archive-probe-20261021'
DETAIL = 'illiquidity-minute-admission-20261021-v2/details.json'
PUBLIC = 'experiments/qlib/'
MIN_REQ = PUBLIC + 'illiquidity-minute-development-request.json'
ADMISSION = PUBLIC + 'illiquidity-development-minute-admission.json'
VERIFY = PUBLIC + 'illiquidity-hf-archive-probe-run-verification.json'
PUBLIC_FILES = (
    MIN_REQ, ADMISSION, VERIFY,
    PUBLIC + 'illiquidity-minute-development-capture-plan.json',
    PUBLIC + 'illiquidity-minute-development-capture-manifest.json',
    PUBLIC + 'illiquidity-raw-source-capture-manifest.json',
    PUBLIC + 'illiquidity-corporate-reviewed-manifest.json',
    PUBLIC + 'illiquidity-corporate-capture-manifest.json',
    PUBLIC + 'illiquidity-source-event-compilation.json',
    PUBLIC + 'illiquidity-hf-archive-probe-request.json',
    PUBLIC + 'illiquidity-hf-archive-probe-independent-audit.json',
    PUBLIC + 'illiquidity-hf-archive-probe-results.json',
    PUBLIC + 'illiquidity-hf-archive-probe-final-review.json',
    PUBLIC + 'illiquidity-hf-archive-metadata-discovery.json',
    PUBLIC + 'illiquidity-archive-cent-clock-code-review.json',
    PUBLIC + 'illiquidity-archive-cent-grid-primary-research.json',
    PUBLIC + 'illiquidity-archive-scenario-builder-code-review.json',
)
METHOD_FILES = tuple(dict.fromkeys((*OLD_METHODS,
    'scripts/build_illiquidity_archive_scenario_sources.py',
    'src/stock_rsi/archive_cent_clock.py', 'src/stock_rsi/archive_minute_probe.py')))
STATUS = 'FROZEN_BEFORE_ARCHIVE_SCENARIO_SOURCE_INTERPRETATION'


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(clean(value), ensure_ascii=False, indent=2) + '\n')


def required_input_paths(base, root):
    """Enumerate mandatory inputs from existing metadata, without quote decoding."""
    paths = {}

    def add(path):
        path = Path(path).resolve()
        if path.is_relative_to(root):
            key = 'repo/' + str(path.relative_to(root))
        else:
            need(path.is_relative_to(base), 'input escapes frozen roots')
            key = 'source/' + str(path.relative_to(base))
        paths[key] = path

    for name in (*PUBLIC_FILES, *METHOD_FILES):
        add(root / name)
    for folder in (RAW, PROOF, EVENTS, OLD, EXTRA):
        add(base / folder / ('reviewed-manifest.json' if folder == PROOF else
                           'summary.json' if folder == EVENTS else 'manifest.json'))
    for name in (TARGET, DETAIL, RAW + '/calendar.json', PROOF + '/capture-manifest.json',
                 OLD + '/plan.json', EXTRA + '/plan.json',
                 'illiquidity-archive-cent-grid-primary-20261022/manifest.json'):
        add(base / name)
    for code in read(base / RAW / 'manifest.json')['per_code_sha256']:
        need(len(code) == 8 and code[:2] in ('SH', 'SZ') and code[2:].isdigit(), 'unsafe code')
        add(base / RAW / 'codes' / (code + '.json'))
    for item in read(base / PROOF / 'reviewed-manifest.json')['documents']:
        need(Path(item['file']).name == item['file'], 'unsafe proof name')
        add(base / PROOF / item['file'])
    for name in read(base / EVENTS / 'summary.json')['artifact_sha256']:
        need(Path(name).name == name, 'unsafe event name')
        add(base / EVENTS / name)
    indexed = {}
    for folder in (OLD, EXTRA):
        for name in read(base / folder / 'manifest.json')['per_session_sha256']:
            need(Path(name).name == name and name.endswith('.json'), 'unsafe tape name')
            need(name not in indexed, 'duplicate original tape')
            indexed[name] = base / folder / 'sessions' / name
    for code, day in read(root / MIN_REQ)['active_requests']:
        need('2024-01-01' <= day <= '2025-12-31', 'development tape scope changed')
        add(indexed[code + '-' + day + '.json'])
    verification = read(root / VERIFY)
    for name in verification['all13_local_output_file_sha256']:
        need(Path(name).name == name, 'unsafe archive artifact')
        add(base / ARCHIVE / name)
    # The old capture's metadata/method inputs are part of its audited provenance.
    for path in read(base / ARCHIVE / 'input-before.json'):
        add(path)
    grid = base / 'illiquidity-archive-cent-grid-primary-20261022'
    for path in grid.iterdir():
        if path.is_file():
            add(path)
    return paths


def verify_request(base, root, request_file, expected_sha):
    need(file_sha(request_file) == expected_sha, 'frozen source request changed')
    request = read(request_file)
    need(request['status'] == STATUS and request['contract'] == CONTRACT
         and request['portfolio_returns_permitted'] is False
         and request['end'] == '2025-12-31', 'source-only contract required')
    need(set(request['method_code_sha256']) == set(METHOD_FILES), 'complete methods required')
    for name, expected in request['method_code_sha256'].items():
        need(file_sha(root / name) == expected, 'frozen method bytes changed')
    paths = required_input_paths(base, root)
    need(set(paths) == set(request['input_sha256']), 'complete input key set required')
    check_hashes(paths, request['input_sha256'])
    return request, paths


def check_hashes(paths, expected):
    need(set(paths) == set(expected), 'input set changed')
    for name, path in paths.items():
        need(file_sha(path) == expected[name], 'frozen source bytes changed: ' + name)


def _interpret(base, root, request, expected_sha, out, progress):
    old_admission = read(root / ADMISSION)
    need(old_admission['admitted_for_reconstructed_execution'] is False
         and old_admission['status_counts'] == {
             'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE': 2247, 'SOURCE_REJECTED': 29}
         and file_sha(base / DETAIL) == old_admission['local_detail_sha256'], 'old failure record changed')
    verification = read(root / VERIFY)
    for name, expected in verification['all13_local_output_file_sha256'].items():
        need(file_sha(base / ARCHIVE / name) == expected, 'original archive bytes changed')
    for path, expected in read(base / ARCHIVE / 'input-before.json').items():
        need(file_sha(path) == expected, 'original archive input changed')
    packets, proof, calendar = authenticate_sources(base / RAW, base / PROOF, base / TARGET, root)
    initial, lifecycle = classify_source_coverage(packets, proof, calendar)
    events, receipts = compile_distribution_events(packets, proof, calendar)
    originals = {'derived_events.json': clean([asdict(e) for e in events]),
                 'event_source_receipts.json': list(receipts),
                 'initial_listing_classification.json': initial,
                 'lifecycle_source_intervals.json': lifecycle}
    for name, value in originals.items():
        need(read(base / EVENTS / name) == value, 'original event compilation changed')
    bars = {code: {r['date']: r for r in p['bars']} for code, p in packets.items()}
    active, skipped = prefix_minute_requirements(read(base / TARGET), bars, proof['lifecycles'])
    old_request = read(root / MIN_REQ)
    need(active == old_request['active_requests'] and skipped == old_request['nonexecuting_source_intervals']
         and len(active) == 2276 and len(skipped) == 18, 'complete fixed prefix changed')
    details = read(base / DETAIL)
    need([(r['instrument'], r['day']) for r in details['sessions']] == [tuple(p) for p in active]
         and details['nonexecuting_source_intervals'] == skipped, 'original admission scope changed')
    rejected = {(r['instrument'], r['day']) for r in details['sessions'] if r['status'] == 'SOURCE_REJECTED'}
    need(sorted(map(list, rejected)) == request['archive_pairs'] and len(rejected) == 29,
         'only original29 failures may use conditional archive route')
    grouped = defaultdict(list)
    for code in sorted({c for c, _ in rejected}):
        for row in read(base / ARCHIVE / (code + '-selected-development-rows.json')):
            row['timestamp'] = datetime.fromisoformat(row['timestamp'])
            key = (code, row['timestamp'].date().isoformat())
            need(key in rejected, 'unrequested archive row')
            grouped[key].append(row)
    need(set(grouped) == rejected and sum(map(len, grouped.values())) == 6989,
         'complete original selected archive rows required')
    bank = TapeBank(base / OLD, base / EXTRA, bars, '2025-12-31')
    records = progress['sessions']
    progress['nonexecuting_source_intervals'] = skipped
    for number, (prior, (code, day)) in enumerate(zip(details['sessions'], active), 1):
        row = {'instrument': code, 'day': day, 'original_status': prior['status'],
               'original_source_sha256': prior['source_sha256']}
        try:
            path, expected = bank.index[(code, day)]
            need(expected == prior['source_sha256'] and file_sha(path) == expected,
                 'original per-session provenance changed')
            if (code, day) in rejected:
                # Confirm the original route is still rejected. No gate override.
                try:
                    bank(code, date.fromisoformat(day))
                except (ValueError, KeyError, AssertionError) as exc:
                    row['original_error_preserved'] = str(exc)
                else:
                    raise ValueError('original rejected tape unexpectedly passed')
                scenario = archive_scenario_windows(code, date.fromisoformat(day), grouped[(code, day)], bars[code][day])
                name = code + '-' + day + '.json'
                write(out / name, scenario)
                windows = scenario['windows']
                row.update(source_kind='CONDITIONAL_ARCHIVE_CENT_CLOCK_INTERSECTION',
                           projection_file=name, projection_sha256=file_sha(out / name),
                           selected_row_count=192, excluded_preserved_row_count=49,
                           whole_day_volume_shares=scenario['whole_day_volume_shares'],
                           safe_window_volume_shares=scenario['safe_window_volume_shares'])
            else:
                need(prior['status'] == 'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE', 'unexpected old status')
                windows = bank(code, date.fromisoformat(day))
                row['source_kind'] = 'UNCHANGED_ORIGINAL_TDX'
            need(len(windows) == 48, 'complete48window session required')
            row.update(status='SOURCE_SCENARIO_COMPLETE', windows=48, window_digest=digest(windows))
        except (ValueError, KeyError, AssertionError) as exc:
            row.update(status='SOURCE_SCENARIO_REJECTED', error=str(exc))
        records.append(row)
        if number % 500 == 0:
            print('source scenario ' + str(number) + '/' + str(len(active)), flush=True)
    counts = dict(Counter(r['status'] for r in records))
    complete = counts == {'SOURCE_SCENARIO_COMPLETE': 2276}
    result = {'status': 'ILLIQUIDITY_CONDITIONAL_SOURCE_SCENARIO_BUILT', 'contract': CONTRACT,
              'request_sha256': expected_sha, 'method_code_sha256': request['method_code_sha256'],
              'required_active_sessions': len(active), 'nonexecuting_source_intervals': len(skipped),
              'original_TDX_sessions': 2247, 'conditional_archive_sessions': 29,
              'status_counts': counts, 'conditional_source_coverage_complete': complete,
              'all_inputs_unchanged': True,
              'input_count': len(request['input_sha256']), 'archive_original_rows': 6989,
              'original_admission_overridden': False, 'admitted_for_original_reconstructed_execution': False,
              'admitted_for_account_replay': False, 'separate_account_freeze_required': True,
              'historical_arrival_verified': False, 'authenticated_provider_or_interval_semantics': False,
              'cent_grid_and_binary32_promotion_are_assumptions': True,
              'SZSE_historical_cent_grid_certified': False, 'OS_future_data_isolation_claimed': False,
              '2026_quote_values_decoded': False, 'portfolio_returns_computed': False,
              'objective_achieved': False,
              'limitations': request['limitations']}
    return result


def build(base, root, request_file, expected_sha, out):
    need(not out.exists(), 'source scenario output already exists')
    request, paths = verify_request(base, root, request_file, expected_sha)
    # Bind the external request separately: it cannot contain its own hash.
    paths = {**paths, 'frozen_request': Path(request_file)}
    expected = {**request['input_sha256'], 'frozen_request': expected_sha}
    out.mkdir(parents=True)
    progress = {'sessions': [], 'nonexecuting_source_intervals': []}
    result, primary, mismatches, persistence_errors = None, None, [], []
    try:
        write(out / 'input-before.json', expected)
        result = _interpret(base, root, request, expected_sha, out, progress)
    except BaseException as exc:
        primary = exc
    finally:
        # Check every input even after an interpretation failure or interrupt.
        for name, path in paths.items():
            try:
                if file_sha(path) != expected[name]:
                    mismatches.append({'input': name, 'reason': 'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input': name, 'reason': type(exc).__name__})
        postcheck = {'all_inputs_unchanged': not mismatches, 'count': len(paths),
                     'request_rehashed_after_processing': True, 'mismatches': mismatches}
        terminal = {'status': 'SOURCE_SCENARIO_BUILD_TERMINAL',
                    'interpretation_completed': result is not None,
                    'original_error': None if primary is None else
                        {'type': type(primary).__name__, 'message': str(primary)},
                    'postcheck': postcheck, 'partial_sessions': len(progress['sessions']),
                    'persistence_errors': persistence_errors,
                    'portfolio_returns_computed': False}
        for name, value in (('details.json', progress), ('input-postcheck.json', postcheck),
                            ('terminal.json', terminal)):
            try:
                write(out / name, value)
            except BaseException as exc:
                persistence_errors.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence_errors:
            primary.add_note('Source terminal persistence failures: ' + str(persistence_errors))
        raise primary
    need(not mismatches, 'frozen inputs changed during source interpretation')
    need(not persistence_errors, 'could not persist terminal source evidence: ' + str(persistence_errors))
    result['details_sha256'] = file_sha(out / 'details.json')
    result['input_count'] = len(paths)
    write(out / 'summary.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'request', 'expected-request-sha256', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    result = build(Path(args.source_root).resolve(), Path(__file__).resolve().parents[1],
                   Path(args.request), args.expected_request_sha256, Path(args.output_dir))
    print(result['status'], result['conditional_source_coverage_complete'], flush=True)


if __name__ == '__main__':
    main()
