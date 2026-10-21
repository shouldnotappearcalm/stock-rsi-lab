"""Extend evaluator events to fixed Oct20 without rewriting prior266 economics."""
import argparse
import copy
from datetime import date
import json
from pathlib import Path

from scripts.prepare_low_beta60_extension_events import METHOD_FILES as PRIOR_METHODS, compile_append_only, serialize_event
from scripts.prepare_low_beta60_account_sources import file_sha
from scripts.run_low_risk_raw_share_validation import validate_source_coverage
from stock_rsi.calendar import TradingCalendar

START, PRIOR_END, END = '2023-12-29', '2026-10-13', '2026-10-20'
OLD_RAW, RAW = 'low-beta60-raw-dev-20261021', 'low-beta60-raw-horizon-20261021'
OLD_EVENTS, PRIOR_EVENTS = 'low-beta60-account-source-events-20261021', 'low-beta60-account-source-events-2026-20261021'
PROOFS, OUTPUT = 'low-beta60-corporate-reviewed-horizon-20261021', 'low-beta60-account-source-events-horizon-20261021'
METHOD_FILES = (*PRIOR_METHODS, 'scripts/prepare_low_beta60_horizon_events.py', 'scripts/run_low_risk_raw_share_validation.py')
LOCAL_FILES = (f'{OLD_RAW}/manifest.json', f'{OLD_RAW}/calendar.json', f'{RAW}/manifest.json', f'{RAW}/calendar.json',
    'low-beta60-horizon-independent-audit-20261021.json', f'{OLD_EVENTS}/summary.json', f'{OLD_EVENTS}/effective_proofs.json',
    f'{OLD_EVENTS}/derived_events.json', f'{OLD_EVENTS}/event_source_receipts.json',
    f'{PRIOR_EVENTS}/summary.json', f'{PRIOR_EVENTS}/derived_events.json', f'{PRIOR_EVENTS}/event_source_receipts.json',
    'low-beta60-extension-event-independent-audit-20261021.json', f'{PROOFS}/reviewed-manifest.json',
    'low-beta60-corporate-reviewed-20261021/reviewed-manifest.json',
    'low-beta60-calendar-extension-formations-20261021/targets.json', 'low-beta60-pre2026-formations-20261021/targets.json')
PUBLIC_FILES = ('experiments/qlib/low-beta60-horizon-source-independent-audit.json',
    'experiments/qlib/low-beta60-horizon-source-output-review.json', 'experiments/qlib/low-beta60-horizon-primary-content-review.json',
    'experiments/qlib/low-beta60-horizon-primary-results.json', 'experiments/qlib/low-beta60-horizon-primary-reviewed-manifest.json',
    'experiments/qlib/audit_sources/2026-10-21-low-beta60-horizon-event-audit.py',
    'docs/research/low-beta60-horizon-event-plan-2026-10-21.md')


def compile_horizon(old_packets, old_proofs, old_events, old_receipts, prior_events, prior_receipts, packets, proofs, calendar):
    events, receipts, stats = compile_append_only(old_packets, old_proofs, old_events, old_receipts, packets, proofs, calendar)
    if len(prior_events) != len(prior_receipts) or not prior_events:
        raise ValueError('nonempty paired prior event artifacts required')
    by_id = {e.event_id: (e, r) for e, r in zip(events, receipts)}
    prior_ids = [e['event_id'] for e in prior_events]
    if len(set(prior_ids)) != len(prior_ids) or len(by_id) != len(events):
        raise ValueError('unique prior and current event identities required')
    ordered, evidence = [], []
    for e, r in zip(prior_events, prior_receipts):
        current = by_id.get(e['event_id'])
        if current is None or serialize_event(current[0]) != e or current[1] != r:
            raise ValueError('prior event economics or source receipts changed')
        ordered.append(current[0]); evidence.append(current[1])
    added = [pair for key, pair in by_id.items() if key not in set(prior_ids)]
    if any(not PRIOR_END < e.ex_date.isoformat() <= END for e, _ in added):
        raise ValueError('new event inserted into previously compiled horizon')
    for e, r in sorted(added, key=lambda pair: (pair[0].ex_date, pair[0].instrument)):
        ordered.append(e); evidence.append(r)
    return tuple(ordered), tuple(evidence), {**stats, 'preserved_prior_events': len(prior_events), 'new_post_Oct13_events': len(added)}


def _read(path): return json.loads(Path(path).read_bytes())


def validate_horizon_coverage(old, packets, events):
    # Unowned future-only names need no pre2026 entitlements. Retain their Dec31 close
    # to check the first2026 reference; every subsequent2026 reference is checked too.
    for scope in ('original69_pre2026', 'all79_2026_with_Dec31_boundary'):
        projected = copy.deepcopy(old if scope == 'original69_pre2026' else packets)
        for p in projected.values():
            p['distributions'] = []
            if scope != 'original69_pre2026':
                p['bars'] = [r for r in p['bars'] if r['date'] >= '2025-12-31']
                p['adjustments'] = [r for r in p['adjustments'] if r['dividOperateDate'] >= '2026-01-01']
        for e in events:
            if (scope == 'original69_pre2026') == (e.ex_date < date(2026, 1, 1)):
                projected[e.instrument]['distributions'].append({'dividOperateDate': e.ex_date.isoformat()})
        validate_source_coverage(projected)


def _packets(base, directory, count, end):
    root = base / directory; manifest = _read(root / 'manifest.json'); sessions = _read(root / 'calendar.json')['sessions']
    if (len(sessions) != count or sessions != sorted(set(sessions)) or [sessions[0], sessions[-1]] != [START, end]
            or manifest['calendar_sha256'] != file_sha(root / 'calendar.json')):
        raise ValueError('explicit source calendar changed')
    packets = {}
    for code, h in manifest['per_code_sha256'].items():
        f = root / 'codes' / (code + '.json')
        if Path(code).name != code or file_sha(f) != h:
            raise ValueError('raw packet bytes changed')
        p = _read(f)
        if p['instrument'] != code or p['window'] != [START, end] or [r['date'] for r in p['bars']] != sessions:
            raise ValueError('complete source identity/calendar required')
        packets[code] = p
    return manifest, sessions, packets


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('plan', 'expected-plan-sha256', 'source-root', 'output-dir'): parser.add_argument('--' + name, required=True)
    a = parser.parse_args(argv); repo = Path(__file__).resolve().parents[1]; base, out = Path(a.source_root), Path(a.output_dir)
    if out.exists() or file_sha(a.plan) != a.expected_plan_sha256:
        raise ValueError('frozen external plan and unused output required')
    plan = _read(a.plan)
    if (plan['status'] != 'FROZEN_LOW_BETA60_OCT20_269_EVENTS_NO_ROI' or plan['window'] != [START, END]
            or plan['output_directory'] != OUTPUT or out.resolve() != (base / OUTPUT).resolve()
            or plan['expected_preserved_events'] != 266 or plan['expected_new_events'] != 3
            or plan['portfolio_returns_to_compute'] is not False or plan['source_queries_allowed'] is not False
            or set(plan['method_code_sha256']) != set(METHOD_FILES)
            or set(plan['local_source_sha256']) != set(LOCAL_FILES) or set(plan['public_evidence_sha256']) != set(PUBLIC_FILES)):
        raise ValueError('fixed horizon compilation scope changed')
    for field, root in (('method_code_sha256', repo), ('local_source_sha256', base), ('public_evidence_sha256', repo)):
        for name, h in plan[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(root / name) != h:
                raise ValueError('bound source, code or evidence changed')
    om, os, old = _packets(base, OLD_RAW, 486, '2025-12-31'); hm, hs, packets = _packets(base, RAW, 676, END)
    audit = _read(base / 'low-beta60-horizon-independent-audit-20261021.json')
    if (hs[:486] != os or len(old) != 69 or len(packets) != 79 or audit['manifest_sha256'] != file_sha(base / RAW / 'manifest.json')
            or audit['all_old_prefixes_unchanged'] is not True or hm['capture_complete'] is not True):
        raise ValueError('independently reconstructed complete raw source required')
    targets = _read(base / 'low-beta60-calendar-extension-formations-20261021/targets.json')['low_beta60']
    oldtargets = _read(base / 'low-beta60-pre2026-formations-20261021/targets.json')['low_beta60']
    if (len(targets) != 34 or {k: v for k, v in targets.items() if k < '2026-01-01'} != oldtargets
            or {c for t in targets.values() for c in t['weights']} != set(packets)):
        raise ValueError('all unchanged34 target formations required')
    for directory in (OLD_EVENTS, PRIOR_EVENTS):
        for name, h in _read(base / directory / 'summary.json')['artifact_sha256'].items():
            if Path(name).name != name or file_sha(base / directory / name) != h:
                raise ValueError('previous event artifact bytes changed')
    prior_audit = _read(base / 'low-beta60-extension-event-independent-audit-20261021.json')
    if prior_audit['summary_sha256'] != file_sha(base / PRIOR_EVENTS / 'summary.json'):
        raise ValueError('prior266 independent evidence changed')
    proofs = _read(base / PROOFS / 'reviewed-manifest.json'); oldproofs = _read(base / OLD_EVENTS / 'effective_proofs.json')
    if proofs['raw_manifest_sha256'] != file_sha(base / RAW / 'manifest.json') or proofs['strict_tax_questions_remaining'] != 1:
        raise ValueError('reviewed horizon proposal and unresolved tax required')
    for proposal, directory in ((proofs, PROOFS), (oldproofs, 'low-beta60-corporate-reviewed-20261021')):
        for d in proposal['documents']:
            if Path(d['file']).name != d['file'] or file_sha(base / directory / d['file']) != d['sha256']:
                raise ValueError('original primary PDF changed')
    prior_events = _read(base / PRIOR_EVENTS / 'derived_events.json'); prior_receipts = _read(base / PRIOR_EVENTS / 'event_source_receipts.json')
    events, receipts, stats = compile_horizon(old, oldproofs, _read(base / OLD_EVENTS / 'derived_events.json'),
        _read(base / OLD_EVENTS / 'event_source_receipts.json'), prior_events, prior_receipts, packets, proofs, TradingCalendar(hs))
    if (stats != {'original_events': 179, 'appended_events': 90, 'earlier_rows_of_future_only_names_ignored': 25,
            'unverified_tax_event_keys': ['SZ000937|2026-06-17'], 'preserved_prior_events': 266, 'new_post_Oct13_events': 3}
            or len(events) != 269):
        raise ValueError('269 event reconciliation differs from frozen scope')
    validate_horizon_coverage(old, packets, events)
    out.mkdir(parents=True)
    for name in ('derived_events.json', 'event_source_receipts.json'):
        (out / ('prior_' + name)).write_bytes((base / PRIOR_EVENTS / name).read_bytes())
    artifacts = {'derived_events.json': [serialize_event(e) for e in events], 'event_source_receipts.json': list(receipts), 'effective_horizon_proofs.json': proofs}
    for name, value in artifacts.items():
        with (out / name).open('x') as f: json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n')
    summary = {'status': '269_EVENTS_COMPILED_PRIOR266_LITERAL_PREFIX_RETAINED_AUDIT_PENDING', 'plan_sha256': a.expected_plan_sha256,
        'window': [START, END], **stats, 'compiled_events': len(events), 'source_queries': 0,
        'raw_manifest_sha256': file_sha(base / RAW / 'manifest.json'), 'proof_manifest_sha256': file_sha(base / PROOFS / 'reviewed-manifest.json'),
        'coverage_scopes_passed': ['original69_pre2026', 'all79_2026_with_Dec31_boundary'],
        'source_kind_counts': {k: sum(r['source_kind'] == k for r in receipts) for k in ('VENDOR_DISTRIBUTION', 'PRIMARY_NOTICE_SUPPLEMENT', 'PRIMARY_CASH_PRECISION_CORRECTION')},
        'artifact_sha256': {n: file_sha(out / n) for n in [*artifacts, 'prior_derived_events.json', 'prior_event_source_receipts.json']},
        'prior266_event_objects_and_receipts_unchanged': True, 'unknown_tax_guard_retained': True,
        'account_replay_admitted': False, 'portfolio_returns_computed': False, 'full_October_complete': False, 'objective_achieved': False}
    with (out / 'summary.json').open('x') as f: json.dump(summary, f, ensure_ascii=False, indent=2); f.write('\n')
    print('compiled269; prior266 literal prefix unchanged; complete2026 reference coverage; noROI', flush=True)
    return 0


if __name__ == '__main__': raise SystemExit(main())
