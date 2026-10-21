"""Append evaluator-only 2026 events while retaining all original255 objects.

No source calls, account replay or returns. Primary interpretations remain
separate from immutable vendor packets and decision-facing target snapshots.
"""
import argparse
import copy
from dataclasses import fields
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from scripts.prepare_low_beta60_account_sources import METHOD_FILES as CORE_METHODS
from scripts.prepare_low_beta60_extension_events import compile_append_only, serialize_event
from scripts.run_low_risk_raw_share_validation import validate_source_coverage
from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import digest
from stock_rsi.listing_anchor_source import project_primary_listing_anchor
from stock_rsi.stock_distribution_account import StockDistribution

START, PRE_END, END = '2023-12-29', '2025-12-31', '2026-10-20'
OLD_RAW = 'szse-value-momentum-raw-dev-20261021'
OLD_EVENTS = 'szse-value-momentum-account-sources-20261021'
FORM = 'szse-value-momentum-formations-full-v2-20261021'
OLD_FORM = 'szse-value-momentum-formations-pre2026-20261021'
RAW = 'szse-value-momentum-raw-full-v2-20261021'
OUTPUT = 'szse-value-momentum-full-account-events-20261021'
INHERITED = 'low-beta60-corporate-reviewed-horizon-20261021/reviewed-manifest.json'
SEVEN_REVIEW = 'experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json'
SUMMARY_STATUS = 'FIXED_COMPOSITE_FULL_SOURCE_EVENTS_COMPILED_NO_RETURNS_AUDIT_PENDING'
ARTIFACTS = ('derived_events.json', 'event_source_receipts.json', 'effective_2026_proofs.json', 'lifecycles.json')
UNRESOLVED = 'SZ000937|2026-06-17'
CAPITAL_KEYS = {'SZ000034|2026-05-19', 'SZ001309|2026-10-13', 'SZ002335|2026-05-29',
                'SZ002595|2026-05-11', 'SZ002837|2026-06-01'}
SUPPLEMENT_KEYS = {'SZ000563|2026-10-20', 'SZ000783|2026-10-20', 'SZ002608|2026-10-19',
                   'SZ002756|2026-10-20', 'SZ002812|2026-10-20', 'SZ003031|2026-10-20'}
METHOD_FILES = tuple(dict.fromkeys((*CORE_METHODS, 'scripts/prepare_low_beta60_extension_events.py',
    'scripts/prepare_value_momentum_full_events.py', 'scripts/fundamental_query_journal.py',
    'scripts/run_low_risk_raw_share_validation.py', 'src/stock_rsi/listing_anchor_source.py')))


def read(path):
    return json.loads(Path(path).read_bytes())


def relative(root, name):
    value = Path(name)
    if value.is_absolute() or '..' in value.parts or not (root/value).resolve().is_relative_to(root.resolve()):
        raise ValueError('safe frozen relative source path required')
    return root/value


def verify_map(root, mapping):
    for name, expected in mapping.items():
        if file_sha(relative(root, name)) != expected:
            raise ValueError('frozen input changed: '+name)


def original_financial_hashes(base):
    result = {}
    for directory, key, labels, artifacts in (
        ('szse-value-momentum-raw-daily-dev-20261021', 'results_by_extra_bps', {'20', '40'},
         {'daily.csv', 'intents.json', 'orders.json', 'fills.json', 'corporate_ledger.json', 'ownership.json'}),
        ('szse-value-momentum-intraday-dev-20261021', 'results_by_profile',
         {f'{capital}/{cost}' for capital in (100, 500, 1000) for cost in (20, 40)},
         {'daily.csv', 'intents.json', 'parent_instructions.json', 'orders.json', 'fills.json', 'corporate_ledger.json', 'ownership.json'})):
        profiles = read(base/directory/'summary.json')[key]
        if set(profiles) != labels:
            raise ValueError('all original financial profiles required')
        for label, profile in profiles.items():
            if set(profile['artifact_sha256']) != artifacts:
                raise ValueError('original financial artifact set changed')
            result.update({f'{directory}/{label}/{n}': h for n, h in profile['artifact_sha256'].items()})
    verify_map(base, result)
    return result


def compile_full(old_packets, old_proofs, old_events, old_receipts, packets, proofs, calendar):
    before = digest([old_packets, old_proofs, old_events, old_receipts, packets, proofs])
    events, receipts, stats = compile_append_only(old_packets, old_proofs, old_events, old_receipts,
                                                 packets, proofs, calendar)
    if stats['unverified_tax_event_keys'] != [UNRESOLVED]:
        raise ValueError('the original unresolved SZ000937 tax guard must remain explicit')
    if ([serialize_event(e) for e in events[:len(old_events)]] != old_events
            or list(receipts[:len(old_receipts)]) != old_receipts):
        raise ValueError('literal original event/receipt order changed')
    if before != digest([old_packets, old_proofs, old_events, old_receipts, packets, proofs]):
        raise ValueError('compiler modified original source or proof objects')
    return events, receipts, stats


def validate_full_coverage(old, packets, events, old_proofs):
    original = copy.deepcopy(old)
    if 'listing_anchor' in old_proofs:
        code = old_proofs['listing_anchor']['instrument']
        sessions = sorted({r['date'] for p in old.values() for r in p['bars']})
        original[code], _ = project_primary_listing_anchor(old[code], old_proofs['listing_anchor'], sessions)
    for old_scope, sources in ((True, original), (False, packets)):
        projected = copy.deepcopy(sources)
        for packet in projected.values():
            # Only explicitly out-of-window quarantine is irrelevant to this
            # evaluator coverage view. Unknown/missing dates remain a failure.
            for item in packet.get('quarantine', []):
                at = item['record'].get('dividOperateDate', '')
                if not (item['reason'] in ('AFTER_EXTENSION_CUTOFF', 'AFTER_CAPTURE_CUTOFF') and at > END
                        or item['reason'] in ('BEFORE_EXTENSION_WINDOW', 'BEFORE_CAPTURE_WINDOW') and at and at < START):
                    raise ValueError('unresolved quarantined distribution')
            packet['quarantine'] = []
            packet['distributions'] = []
            if not old_scope:
                packet['bars'] = [r for r in packet['bars'] if r['date'] >= PRE_END]
                packet['adjustments'] = [r for r in packet['adjustments'] if r['dividOperateDate'] >= '2026-01-01']
                if not packet['bars'] or packet['bars'][0]['date'] != PRE_END:
                    raise ValueError('every2026 source needs the actual Dec31 reference boundary')
        for event in events:
            if old_scope == (event.ex_date < date(2026, 1, 1)):
                projected[event.instrument]['distributions'].append({'dividOperateDate': event.ex_date.isoformat()})
        validate_source_coverage(projected)


def _artifact_hashes(directory, summary):
    for name, expected in summary['artifact_sha256'].items():
        if Path(name).name != name or file_sha(directory/name) != expected:
            raise ValueError('compiled source artifact changed: '+name)


def _load_packets(base, directory, sessions, end, expected_names):
    root = base/directory; manifest = read(root/'manifest.json')
    if (file_sha(root/'calendar.json') != manifest['calendar_sha256']
            or read(root/'calendar.json')['sessions'] != sessions or len(manifest['per_code_sha256']) != expected_names):
        raise ValueError('explicit calendar and complete source universe required')
    packets = {}
    for code, h in manifest['per_code_sha256'].items():
        if Path(code).name != code or file_sha(root/'codes'/(code+'.json')) != h:
            raise ValueError('original source packet changed')
        packet = read(root/'codes'/(code+'.json'))
        required = [d for d in sessions if code != 'SZ001389' or d >= '2024-04-02']
        if packet['instrument'] != code or packet['window'] != [START, end] or [r['date'] for r in packet['bars']] != required:
            raise ValueError('complete raw date identity or sole registered listing boundary changed')
        packets[code] = packet
    return manifest, packets


def load_full_inputs(source_root, plan, repo_root):
    base, repo = Path(source_root), Path(repo_root)
    if (plan['status'] != 'FROZEN_COMPOSITE_FULL_APPEND_ONLY_EVENTS_NO_ROI'
            or plan['candidate'] != 'szse_value_momentum_equal' or plan['window'] != [START, END]
            or plan['output_directory'] != OUTPUT or plan['raw_v2_directory'] != RAW
            or plan['source_queries_allowed'] is not False or plan['portfolio_returns_to_compute'] is not False
            or plan['expected_preserved_events'] != 255 or plan['expected_compiled_events'] != 410
            or set(plan['method_code_sha256']) != set(METHOD_FILES)):
        raise ValueError('fixed composite source-event scope required')
    local_required = {OLD_RAW+'/manifest.json', OLD_RAW+'/calendar.json', RAW+'/manifest.json', RAW+'/calendar.json',
        OLD_EVENTS+'/summary.json', OLD_EVENTS+'/reviewed-manifest.json', OLD_EVENTS+'/derived_events.json',
        OLD_EVENTS+'/event_source_receipts.json', OLD_EVENTS+'/lifecycles.json', OLD_EVENTS+'/listing_anchor_receipt.json',
        FORM+'/receipt.json', FORM+'/targets.json', OLD_FORM+'/targets.json', OLD_FORM+'/formation_receipts.json', INHERITED,
        plan['raw_v2_audit_file'], plan['reviewed_2026_manifest_file']}
    reviews = plan['primary_content_review_sha256']
    if (len(reviews) != 2 or SEVEN_REVIEW not in reviews
            or not local_required <= set(plan['local_source_sha256'])
            or not set(reviews) <= set(plan['public_evidence_sha256'])):
        raise ValueError('all old artifacts, V2 audit and both new content reviews must be bound')
    for parent, mapping in ((repo, plan['method_code_sha256']), (repo, plan['public_evidence_sha256']),
                             (base, plan['local_source_sha256']), (repo, reviews), (base, plan['primary_document_sha256'])):
        verify_map(parent, mapping)
    financial = original_financial_hashes(base)
    if len(financial) != 54 or financial != plan['financial_artifact_sha256']:
        raise ValueError('all original42intraday and12daily artifacts must remain unchanged')
    sessions = read(base/RAW/'calendar.json')['sessions']; old_sessions = read(base/OLD_RAW/'calendar.json')['sessions']
    if (sessions != sorted(set(sessions)) or len(sessions) != 676 or len(old_sessions) != 486
            or sessions[:486] != old_sessions or [sessions[0], sessions[-1]] != [START, END]):
        raise ValueError('explicit676 sessions and486 original prefix required')
    om, old = _load_packets(base, OLD_RAW, old_sessions, PRE_END, 103)
    m, packets = _load_packets(base, RAW, sessions, END, 127)
    if (m['status'] != 'LOCAL_ONLY_V2_RAW_REASSEMBLED_ADMISSION_SEPARATE'
            or m['source_inputs_unchanged_after_reassembly'] is not True or m['source_queries'] != 0
            or m['original103_pre2026_rows_literal_equal'] is not True
            or m['original42_intraday_and12_daily_hashes_unchanged'] is not True
            or m['original_v1_capture_errors_cleared'] is not False):
        raise ValueError('independent local-only V2 source reconstruction required')
    audit = read(relative(base, plan['raw_v2_audit_file']))
    if (audit['raw_manifest_sha256'] != file_sha(base/RAW/'manifest.json') or audit['source_queries'] != 0
            or audit['portfolio_returns_computed'] is not False or any(audit[k] is not True for k in
                ('all127_packets_authenticated', 'all123_accepted_packets_byte_exact',
                 'all_original103_prefixes_identical', 'all54_original_financial_files_unchanged'))
            or set(audit['coordinate_revisions']) != {'SZ000563', 'SZ000783', 'SZ002608', 'SZ002756'}):
        raise ValueError('all source/prefix/coordinate V2 checks required')
    receipt = read(base/FORM/'receipt.json'); _artifact_hashes(base/FORM, receipt)
    targets = read(base/FORM/'targets.json'); families = read(base/FORM/'family_targets.json')
    oldfamilies = {name: {d: t for d, t in rows.items() if d < '2026-01-01'} for name, rows in families.items()}
    oldreceipts = [r for r in read(base/FORM/'formation_receipts.json') if r['execution_session'] < '2026-01-01']
    if (len(targets) != 34 or {c for t in targets.values() for c in t['weights']} != set(packets)
            or (json.dumps(oldfamilies, indent=2)+'\n').encode() != (base/OLD_FORM/'targets.json').read_bytes()
            or (json.dumps(oldreceipts, indent=2)+'\n').encode() != (base/OLD_FORM/'formation_receipts.json').read_bytes()):
        raise ValueError('all34 targets and complete24month original family/receipt byte prefix required')
    old_summary = read(base/OLD_EVENTS/'summary.json'); _artifact_hashes(base/OLD_EVENTS, old_summary)
    old_proofs = read(base/OLD_EVENTS/'reviewed-manifest.json'); old_events = read(base/OLD_EVENTS/'derived_events.json')
    old_receipts = read(base/OLD_EVENTS/'event_source_receipts.json'); lifecycles = read(base/OLD_EVENTS/'lifecycles.json')
    if len(old_events) != 255 or len(old_receipts) != 255 or old_summary['raw_manifest_sha256'] != file_sha(base/OLD_RAW/'manifest.json'):
        raise ValueError('original255 paired source events required')
    proofs = read(relative(base, plan['reviewed_2026_manifest_file']))
    if (proofs['raw_manifest_sha256'] != file_sha(base/RAW/'manifest.json')
            or proofs['content_review_sha256'] != reviews or proofs['strict_statutory_tax_certification'] is not False
            or set(proofs['capital_tax']) != CAPITAL_KEYS or set(proofs['unresolved_tax']) != {UNRESOLVED}
            or set(proofs['cash_overrides']) != set(plan['expected_cash_precision_keys'])
            or 'SZ000975|2026-04-24' not in proofs['cash_overrides']
            or {x['instrument']+'|'+x['record']['dividOperateDate'] for x in proofs['supplementary_distributions']} != SUPPLEMENT_KEYS
            or len(proofs['supplementary_distributions']) != 6):
        raise ValueError('five limited inferences, one unresolved tax event and six unique cash supplements required')
    for proof in proofs['capital_tax'].values():
        if proof.get('verified_exempt') is not True or proof.get('evidence_kind') != 'PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE':
            raise ValueError('new capital interpretation must retain its explicitly limited inference class')
    inherited = read(base/INHERITED)
    if (proofs['unresolved_tax'] != inherited['unresolved_tax']
            or proofs['cash_overrides']['SZ000975|2026-04-24'] != inherited['cash_overrides']['SZ000975|2026-04-24']):
        raise ValueError('existing unknown-tax marker and issuer cash precision interpretation must remain literal')
    documents = {Path(n).name: (n, h) for n, h in plan['primary_document_sha256'].items()}
    if len(documents) != len(plan['primary_document_sha256']):
        raise ValueError('one bound primary path per document filename required')
    required_docs = {}
    for proposal in (old_proofs, proofs):
        for document in proposal['documents']:
            key = document['file']
            if key not in documents or document['sha256'] != documents[key][1]:
                raise ValueError('every old/new proof document must bind authenticated original PDF bytes')
            if not relative(base, documents[key][0]).read_bytes().startswith(b'%PDF'):
                raise ValueError('original primary PDF required')
            required_docs[key] = document['sha256']
    if set(required_docs) != set(documents):
        raise ValueError('unconsumed primary document binding')
    return {'plan': plan, 'calendar': TradingCalendar(sessions), 'old_packets': old, 'packets': packets,
            'old_proofs': old_proofs, 'old_events': old_events, 'old_receipts': old_receipts,
            'proofs': proofs, 'lifecycles': lifecycles, 'financial_artifact_sha256': financial}


def load_full_events(event_dir, expected_summary_sha256):
    root = Path(event_dir)
    if file_sha(root/'summary.json') != expected_summary_sha256:
        raise ValueError('compiled event summary identity changed')
    summary = read(root/'summary.json')
    if (summary['status'] != SUMMARY_STATUS or set(summary['artifact_sha256']) != set(ARTIFACTS)
            or summary['all_original_events_and_receipts_reconstructed_unchanged'] is not True
            or summary['unknown_tax_requires_zero_registered_ownership'] is not True
            or summary['account_replay_admitted'] is not False or summary['portfolio_returns_computed'] is not False):
        raise ValueError('hash-bound unscored compiled event artifact set required')
    _artifact_hashes(root, summary)
    events = []
    expected_fields = {field.name for field in fields(StockDistribution)}
    for row in read(root/'derived_events.json'):
        if set(row) != expected_fields:
            raise ValueError('exact StockDistribution schema required')
        value = dict(row)
        for key in ('announced', 'recorded', 'ex_date', 'pay_date', 'listed'):
            text = value[key]
            if text is None and key in ('pay_date', 'listed'): continue
            parsed = date.fromisoformat(text)
            if parsed.isoformat() != text: raise ValueError('canonical event date required')
            value[key] = parsed
        for key in ('cash_per_share', 'capital_per_share', 'stock_per_share', 'stock_taxable_income_per_share'):
            if not isinstance(value[key], str): raise ValueError('Decimal event values must retain serialized strings')
            value[key] = Decimal(value[key])
            if not value[key].is_finite() or value[key] < 0: raise ValueError('finite nonnegative event values required')
        for key in ('capital_tax_exempt_verified', 'stock_tax_basis_verified'):
            if type(value[key]) is not bool: raise ValueError('typed tax flags required')
        events.append(StockDistribution(**value))
    receipts = read(root/'event_source_receipts.json'); proofs = read(root/'effective_2026_proofs.json')
    unsafe = sorted(r['instrument']+'|'+r['ex_date'] for r in receipts if r['requires_zero_record_ownership_if_tax_unverified'])
    guarded = [e for e in events if e.instrument+'|'+e.ex_date.isoformat() == UNRESOLVED]
    if (len(events) != summary['compiled_events'] or len(receipts) != len(events)
            or len({e.event_id for e in events}) != len(events)
            or [e.event_id for e in events] != [r['event_id'] for r in receipts]
            or unsafe != [UNRESOLVED] or set(proofs['unresolved_tax']) != {UNRESOLVED}
            or proofs['unresolved_tax'][UNRESOLVED].get('verified_exempt') is not False
            or UNRESOLVED in proofs.get('capital_tax', {}) or len(guarded) != 1
            or guarded[0].capital_per_share <= 0 or guarded[0].capital_tax_exempt_verified is not False):
        raise ValueError('paired event identities and original unknown-tax guard required')
    return tuple(events), read(root/'lifecycles.json'), summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'plan', 'expected-plan-sha256', 'output-dir'): parser.add_argument('--'+name, required=True)
    args = parser.parse_args(argv); base = Path(args.source_root); repo = Path(__file__).resolve().parents[1]; out = Path(args.output_dir)
    if out.exists() or file_sha(args.plan) != args.expected_plan_sha256:
        raise ValueError('unused output and frozen external plan required')
    plan = read(args.plan)
    if out.resolve() != (base/OUTPUT).resolve(): raise ValueError('fixed separate event output required')
    loaded = load_full_inputs(base, plan, repo)
    events, receipts, stats = compile_full(*(loaded[n] for n in ('old_packets', 'old_proofs', 'old_events',
        'old_receipts', 'packets', 'proofs', 'calendar')))
    if stats['original_events'] != 255 or len(events) != 410 or stats['appended_events'] != 155:
        raise ValueError('complete255 plus149vendor2026 plus6primary event reconciliation required')
    validate_full_coverage(loaded['old_packets'], loaded['packets'], events, loaded['old_proofs'])
    # Authenticate again before publishing; no original data or financial artifact is changed.
    load_full_inputs(base, plan, repo)
    if file_sha(args.plan) != args.expected_plan_sha256: raise ValueError('external plan changed during compilation')
    artifacts = {'derived_events.json': [serialize_event(e) for e in events], 'event_source_receipts.json': list(receipts),
                 'effective_2026_proofs.json': loaded['proofs'], 'lifecycles.json': loaded['lifecycles']}
    out.mkdir()
    for name, value in artifacts.items():
        with (out/name).open('x') as stream: json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False); stream.write('\n')
    summary = {'status': SUMMARY_STATUS, 'plan_sha256': args.expected_plan_sha256, 'window': [START, END],
        **stats, 'compiled_events': len(events), 'raw_manifest_sha256': file_sha(base/RAW/'manifest.json'),
        'target_sha256': file_sha(base/FORM/'targets.json'), 'original_summary_sha256': file_sha(base/OLD_EVENTS/'summary.json'),
        'coverage_scopes_passed': ['original103_pre2026', 'all127_2026_with_Dec31_boundary'],
        'artifact_sha256': {n: file_sha(out/n) for n in ARTIFACTS},
        'source_kind_counts': {kind: sum(r['source_kind'] == kind for r in receipts) for kind in
            ('VENDOR_DISTRIBUTION', 'PRIMARY_NOTICE_SUPPLEMENT', 'PRIMARY_CASH_PRECISION_CORRECTION')},
        'all_original_events_and_receipts_reconstructed_unchanged': True,
        'original42_intraday_and12_daily_hashes_unchanged': True, 'original_source_files_modified': False,
        'unknown_tax_requires_zero_registered_ownership': True, 'strict_statutory_tax_certification': False,
        'source_queries': 0, 'event_compilation_independently_verified': False, 'account_replay_admitted': False,
        'historical_arrival_verified': False, 'actual_FIFO_tax_liability_verified': False,
        'full_corporate_actions_certified': False, 'portfolio_returns_computed': False,
        'full_October_complete': False, 'investment_rules_changed': False, 'objective_achieved': False}
    with (out/'summary.json').open('x') as stream: json.dump(summary, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print('Compiled410source events; original255 prefix unchanged; unknown tax guard retained; no account/ROI')
    return 0


if __name__ == '__main__': raise SystemExit(main())
