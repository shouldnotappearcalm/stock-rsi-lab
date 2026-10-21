"""One frozen source-only capture for the unchanged price-delay horizon.

Reuse the original journal/assembly code. Preserve all source bytes and known
coordinate proofs; do not run an account or compute a portfolio return.
"""
import argparse
import copy
import json
import socket
from importlib.metadata import version
from pathlib import Path

from scripts.fundamental_query_journal import digest, file_sha, write_packet_once
from scripts.value_momentum_raw_extension_sources import (
    START, PRE_END, END, SourceSession, baseline_from_cache, capture_packets,
    compose_packet, partition, validate_bars, verify_overlap,
)
from scripts.reassemble_value_momentum_raw_extension_v2 import (
    METHOD_FILES as COORDINATE_METHODS, verify_coordinate_transition,
)
from scripts.prepare_price_delay_horizon_formations import immutable_financial_hashes, FINANCIAL_FILES

SOURCES = ('szse-value-momentum-raw-full-v2-20261021', 'low-beta60-raw-horizon-20261021',
           'reversal-raw-full-20261017', 'szse-value-raw-full-20261017')
OLD = 'price-delay-raw-dev-20261021'
FORM = 'price-delay-horizon-formations-20261021'
OUTPUT = 'price-delay-raw-horizon-20261021'
PRIMARY = 'szse-value-momentum-primary-2026-gaps-20261021'
REVIEW = 'experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json'
INVENTORY = 'experiments/qlib/price-delay-horizon-raw-inventory.json'
ROUTES = 'experiments/qlib/price-delay-horizon-raw-route-plan.json'
PROTOCOL = 'docs/research/price-delay-horizon-raw-source-plan-2026-10-21.md'
COORDINATE_KEYS = tuple(c + '/' + root for c in ('SZ002608', 'SZ002756') for root in SOURCES[2:])
METHOD_FILES = tuple(dict.fromkeys((*COORDINATE_METHODS,
    'scripts/capture_price_delay_horizon_raw.py', 'scripts/prepare_price_delay_horizon_formations.py')))
PUBLIC_FILES = (INVENTORY, ROUTES, REVIEW, PROTOCOL,
    'experiments/qlib/price-delay-horizon-raw-inventory-review.json',
    'experiments/qlib/price-delay-horizon-raw-inventory-verification.json',
    'experiments/qlib/price-delay-horizon-formation-results.json',
    'experiments/qlib/price-delay-horizon-formation-independent-audit.json',
    'experiments/qlib/price-delay-horizon-formation-verification.json',
    'experiments/qlib/audit_sources/2026-10-21-price-delay-horizon-formation-audit.py',
    'experiments/qlib/price-delay-horizon-existing-coordinate-reuse-audit.json',
    'experiments/qlib/audit_sources/2026-10-21-price-delay-horizon-existing-coordinate-reuse-audit.py')
LOCAL_FILES = (OLD + '/manifest.json', OLD + '/calendar.json', FORM + '/candidate_targets.json',
    FORM + '/summary.json', PRIMARY + '/manifest.json', SOURCES[0] + '/coordinate_checks.json')
BINDINGS = (('method_code_sha256', METHOD_FILES), ('public_evidence_sha256', PUBLIC_FILES),
            ('local_source_sha256', LOCAL_FILES))
PROFILE = {'status': 'FROZEN_PRICE_DELAY_HORIZON_RAW_SOURCE_CAPTURE', 'candidate': 'price_delay_d1',
    'window': [START, END], 'source_priority': list(SOURCES), 'names': 203, 'whole_cache_names': 102,
    'incremental_names': 80, 'cold_names': 21, 'maximum_source_reservations': 345,
    'max_attempts_per_query': 1, 'maximum_consecutive_failed_codes': 3,
    'maximum_administrative_login_attempts': 1, 'socket_timeout_seconds': 20,
    'baostock_version': '0.9.4', 'output_directory': OUTPUT, 'protocol_file': PROTOCOL,
    'coordinate_reference_keys': list(COORDINATE_KEYS),
    'portfolio_returns_to_compute': False, 'investment_rules_changed': False,
    'full_October_2026_complete': False, 'source_admitted_for_account_replay': False}


def read(path):
    return json.loads(Path(path).read_text())


def safe(root, name):
    if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('safe relative frozen path required')
    result = Path(root) / name
    if not result.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('frozen source path escapes root')
    return result


def check_scope(r):
    if (any(type(r.get(k)) is not type(v) or r[k] != v for k, v in PROFILE.items())
            or any(set(r[field]) != set(names) for field, names in BINDINGS)
            or set(r['immutable_financial_sha256']) != set(FINANCIAL_FILES)
            or set(r['coordinate_reference_proof_sha256']) != set(COORDINATE_KEYS)):
        raise ValueError('fixed203/102/80/21/345 source-only protocol required')


def verify_cached_reference(code, root, selected, reference, notice, saved):
    """Use only an already saved, exact coordinate proof; no source rewrite."""
    key = code + '/' + root
    if key not in COORDINATE_KEYS:
        verify_overlap(selected, reference)
        return None
    fresh = {'instrument': code, 'window': ['2026-01-01', END]}
    for name, field in (('bars', 'date'), ('distributions', 'dividOperateDate'), ('adjustments', 'dividOperateDate')):
        fresh[name] = copy.deepcopy([r for r in selected[name] if r[field] > PRE_END])
    proof = verify_coordinate_transition(fresh, reference, notice)
    if not any(digest(proof) == digest(p) for p in saved.get(code, [])):
        raise ValueError('exact pre-existing independently reviewed coordinate proof required')
    return proof


def verify_coordinate_audit(audit, r, repo, base):
    if (audit['existing_proof_can_be_reused_unchanged'] is not True
            or audit['imports_project_code'] is not False
            or audit['production_coordinate_function_called'] is not False
            or audit['raw_source_bytes_modified'] is not False
            or audit['cash_or_tax_inferred_from_adjustment_factors'] is not False
            or audit['account_or_ROI_computed'] is not False
            or audit['network_calls'] != 0 or audit['critical_or_important_findings']
            or audit['audit_code_sha256'] != file_sha(repo / PUBLIC_FILES[-1])
            or audit['V2_manifest_sha256'] != file_sha(base / SOURCES[0] / 'manifest.json')
            or audit['coordinate_checks_sha256'] != file_sha(base / SOURCES[0] / 'coordinate_checks.json')
            or audit['seven_notice_content_review_sha256'] != file_sha(repo / REVIEW)
            or audit['seven_notice_capture_manifest_sha256'] != file_sha(base / PRIMARY / 'manifest.json')
            or len(audit['pairs']) != 4
            or {x['instrument'] + '/' + x['cached_root']: x['existing_proof_sha256']
                for x in audit['pairs']} != r['coordinate_reference_proof_sha256']
            or len(audit['semantic_negative_controls_rejected']) != 4
            or any(v is not True for v in audit['semantic_negative_controls_rejected'].values())):
        raise ValueError('independent four-pair coordinate audit required')


def authenticate_request(path, expected_sha, repo, base):
    if file_sha(path) != expected_sha:
        raise ValueError('frozen request checksum changed')
    r = read(path)
    check_scope(r)
    for field, parent in (('method_code_sha256', repo), ('public_evidence_sha256', repo),
                          ('local_source_sha256', base), ('immutable_financial_sha256', base)):
        for name, h in r[field].items():
            if file_sha(safe(parent, name)) != h:
                raise ValueError('frozen method/source/evidence changed: ' + name)
    if immutable_financial_hashes(base) != r['immutable_financial_sha256']:
        raise ValueError('all48 pre2026 financial artifacts must remain unchanged')
    verify_coordinate_audit(read(repo / PUBLIC_FILES[-2]), r, repo, base)
    inv, routes = read(repo / INVENTORY), read(repo / ROUTES)
    fa, fv = read(repo / PUBLIC_FILES[7]), read(repo / PUBLIC_FILES[8])
    fs = read(base / FORM / 'summary.json')
    iv, ir = read(repo / PUBLIC_FILES[5]), read(repo / PUBLIC_FILES[4])
    if (inv['source_priority_fixed_before_inventory'] != list(SOURCES)
            or inv['original_prefix_differences'] or inv['common_date_core_conflicts']
            or iv['inventory_sha256'] != file_sha(repo / INVENTORY)
            or iv['independent_review_sha256'] != file_sha(repo / PUBLIC_FILES[4])
            or iv['root_review_reproduction_byte_identical'] is not True
            or ir['checks']['all_203_per_code_items_exactly_reconstructed'] is not True
            or fa['all34_formations_independently_reconstructed'] is not True
            or fa['original24_prefix_identical'] is not True or fa['imports_project_code'] is not False
            or fa['audit_code_sha256'] != file_sha(repo / PUBLIC_FILES[9])
            or fa['summary_sha256'] != file_sha(base / FORM / 'summary.json')
            or fv['root_reproduction_byte_identical'] is not True
            or fv['independent_audit_sha256'] != file_sha(repo / PUBLIC_FILES[7])
            or fs != read(repo / PUBLIC_FILES[6])):
        raise ValueError('independent fixed formation and source-inventory proof required')
    target = base / FORM / 'candidate_targets.json'
    if (file_sha(target) != r['target_sha256'] or r['target_sha256'] != inv['target_sha256']
            or r['target_sha256'] != routes['target_sha256']
            or fs['artifact_sha256']['candidate_targets.json'] != r['target_sha256']
            or routes['inventory_sha256'] != file_sha(repo / INVENTORY)
            or routes['routes'] != r['cache_routes']):
        raise ValueError('frozen target and source route identities changed')
    targets = read(target)
    codes = sorted({c for t in targets.values() for c in t['weights']})
    if codes != r['codes'] or len(codes) != 203 or len(targets) != 34:
        raise ValueError('complete203name34target scope required')
    if set(r['source_manifest_sha256']) != set(SOURCES) or set(r['source_calendar_sha256']) != set(SOURCES):
        raise ValueError('all four fixed cache manifests and calendars required')
    manifests = {}
    for name in SOURCES:
        root = base / name
        if (file_sha(root / 'manifest.json') != r['source_manifest_sha256'][name]
                or r['source_manifest_sha256'][name] != inv['source_manifest_sha256'][name]):
            raise ValueError('registered cache manifest changed')
        manifests[name] = read(root / 'manifest.json')
        if (file_sha(root / 'calendar.json') != r['source_calendar_sha256'][name]
                or manifests[name]['calendar_sha256'] != r['source_calendar_sha256'][name]):
            raise ValueError('registered cache calendar changed')
    sessions = read(base / SOURCES[1] / 'calendar.json')['sessions']
    if (sessions != sorted(set(sessions)) or len(sessions) != 676 or [sessions[0], sessions[-1]] != [START, END]
            or sessions[:486] != read(base / OLD / 'calendar.json')['sessions']):
        raise ValueError('676 explicit source sessions and identical486 prefix required')
    for root in SOURCES:
        end = min(END, manifests[root]['window'][1])
        if read(base / root / 'calendar.json')['sessions'] != [d for d in sessions if d <= end]:
            raise ValueError('registered source calendar disagreement')
    primary, content = read(base / PRIMARY / 'manifest.json'), read(repo / REVIEW)
    newest = manifests[SOURCES[0]]
    if (file_sha(base / PRIMARY / 'manifest.json') != content['capture_manifest_sha256']
            or newest['primary_manifest_sha256'] != file_sha(base / PRIMARY / 'manifest.json')
            or newest['primary_content_review_sha256'] != file_sha(repo / REVIEW)
            or newest['coordinate_checks_sha256'] != file_sha(base / SOURCES[0] / 'coordinate_checks.json')
            or content['all28pages_independently_text_extracted_and_visually_reviewed'] is not True):
        raise ValueError('original coordinate/primary content provenance changed')
    reviews = {x['instrument']: x for x in content['documents']}
    for code in ('SZ002608', 'SZ002756'):
        doc, review = primary['documents'][code], reviews[code]
        pdf = safe(base / PRIMARY, doc['file'])
        if (file_sha(pdf) != doc['sha256'] or not pdf.read_bytes().startswith(b'%PDF')
                or any(doc[k] != review[k] for k in ('instrument', 'file', 'sha256', 'publication_day'))):
            raise ValueError('original issuer notice bytes changed')
        for kind in ('request', 'reserved', 'response'):
            receipt = doc['pdf_receipt']
            if file_sha(safe(base / PRIMARY, receipt[kind + '_file'])) != receipt[kind + '_sha256']:
                raise ValueError('original PDF receipt bytes changed')
    saved = read(base / SOURCES[0] / 'coordinate_checks.json')
    original = read(base / OLD / 'manifest.json')
    if (original['per_code_sha256'] != r['original_packet_sha256'] or len(original['per_code_sha256']) != 151
            or file_sha(base / OLD / 'manifest.json') != inv['original_raw_manifest_sha256']
            or file_sha(base / OLD / 'calendar.json') != original['calendar_sha256']):
        raise ValueError('original151 source/calendar identity changed')
    baselines, lineage = {}, {}
    for code, h in original['per_code_sha256'].items():
        f = base / OLD / 'codes' / (code + '.json')
        if file_sha(f) != h:
            raise ValueError('original raw prefix bytes changed')
        v = read(f)
        if v['instrument'] != code or v['window'] != [START, PRE_END] or [x['date'] for x in v['bars']] != sessions[:486]:
            raise ValueError('original151 complete raw histories required')
        baselines[code] = v
        lineage[code] = {'baseline': {'kind': 'ORIGINAL_PRICE_DELAY_PREFIX', 'file': str(f.relative_to(base)), 'sha256': h}}
    cached, overlaps, proofs = {}, {}, {}
    for code in codes:
        item = inv['items'][code]
        payloads = []
        for choice in item['choices']:
            name = choice['root']
            if name not in SOURCES:
                raise ValueError('unregistered cache root')
            f = base / name / 'codes' / (code + '.json')
            if file_sha(f) != choice['packet_sha256'] or manifests[name]['per_code_sha256'][code] != choice['packet_sha256']:
                raise ValueError('cached packet bytes changed')
            p = read(f)
            if p['instrument'] != code or p['window'] != choice['window']:
                raise ValueError('cached issuer/window changed')
            validate_bars(code, p['bars'])
            if [x['date'] for x in p['bars']] != [d for d in sessions if d <= p['window'][1]]:
                raise ValueError('unexplained source gap; no listing or synthetic-price exception')
            if code in baselines:
                verify_overlap(baselines[code], p)
            payloads.append((name, p, choice))
        route = r['cache_routes'][code]
        if not payloads:
            if route['source_class'] != ('incremental' if code in baselines else 'cold'):
                raise ValueError('empty-cache route changed')
            continue
        selected_name = route['cache_route']
        selected = next(p for name, p, _ in payloads if name == selected_name)
        good = []
        for name, p, _ in payloads:
            proof = verify_cached_reference(code, name, selected, p, reviews.get(code), saved)
            if proof is None:
                good.append(p)
            else:
                proofs[code + '/' + name] = proof
        overlaps[code] = good
        lineage.setdefault(code, {})['registered_caches'] = item['choices']
        if code not in baselines and route['source_class'] == 'incremental':
            baselines[code] = baseline_from_cache(code, selected, sessions)
            lineage[code]['baseline'] = {'kind': 'CLIPPED_FIXED_PARTIAL_CACHE_PREFIX', 'root': selected_name,
                                        'packet_sha256': route['cache_packet_sha256']}
        if route['source_class'] == 'whole_cache':
            compose_packet(code, selected, baselines.get(code), sessions, caches=good)
            cached[code] = selected
        lineage[code]['retained_coordinate_variance_proofs'] = {
            key: digest(value) for key, value in proofs.items() if key.startswith(code + '/')}
    derived = partition(codes, baselines, cached)
    if (len(cached) != 102 or len(baselines) != 167 or len(derived['incremental']) != 80
            or len(derived['cold']) != 21 or derived['budget'] != 345
            or derived['fresh'] != r['fresh_codes'] or sorted(baselines) != r['baseline_codes']
            or {key: digest(value) for key, value in proofs.items()} != r['coordinate_reference_proof_sha256']):
        raise ValueError('fixed102/80/21 source partition or original coordinate proof changed')
    return r, codes, sessions, baselines, cached, overlaps, lineage, proofs


def capture_complete(manifest, cleanup, postcheck, login, codes):
    return (manifest['requested_names'] == manifest['names'] == 203
        and sorted(manifest['per_code_sha256']) == codes and len(codes) == 203
        and not manifest['errors_sha256'] and not manifest['pending_codes']
        and manifest['abnormal_exit'] is None and manifest['maximum_source_reservations'] == 345
        and manifest['query_reservations_consumed'] == 345
        and cleanup.get('login_attempted') is True and cleanup.get('logout_attempted') is True
        and cleanup.get('error_code') == '0' and 'error' not in cleanup
        and login.get('error_code') == '0' and postcheck['source_inputs_unchanged_after_capture'] is True)


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ('source-root', 'request', 'expected-request-sha256', 'output-dir'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--preflight-only', action='store_true')
    a = p.parse_args(argv)
    base, repo, out = Path(a.source_root), Path(__file__).resolve().parents[1], Path(a.output_dir)
    if out.exists():
        raise ValueError('preserve existing source capture; no resume')
    context = authenticate_request(a.request, a.expected_request_sha256, repo, base)
    r, codes, sessions, baselines, cached, overlaps, lineage, proofs = context
    if out.resolve() != (base / OUTPUT).resolve() or version('baostock') != r['baostock_version']:
        raise ValueError('fixed output or SDK version changed')
    if a.preflight_only:
        print('preflight203names/102cache/80incremental/21cold/345queries; no network/output/account', flush=True)
        return 0
    import baostock as sdk
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(20)
    session = SourceSession(out, a.expected_request_sha256, sdk)
    complete = False
    try:
        manifest = capture_packets(out, codes, sessions, baselines, cached, a.expected_request_sha256, session,
            overlaps=overlaps, lineage=lineage, request_bytes=Path(a.request).read_bytes())
    finally:
        try:
            if out.exists():
                session.close()
                checked = {'source_inputs_unchanged_after_capture': False}
                try:
                    authenticate_request(a.request, a.expected_request_sha256, repo, base)
                except Exception as exc:
                    checked.update(error_type=type(exc).__name__, error=str(exc))
                else:
                    checked['source_inputs_unchanged_after_capture'] = True
                write_packet_once(out / 'source-postcheck.json', checked)
                write_packet_once(out / 'coordinate-reference-proofs.json', proofs)
                if (out / 'manifest.json').exists():
                    m = read(out / 'manifest.json')
                    complete = capture_complete(m, read(out / 'cleanup.json'), checked,
                        read(out / 'login-response-1.json') if (out / 'login-response-1.json').exists() else {}, codes)
                    write_packet_once(out / 'price-delay-scope.json', {
                        'status': 'PRICE_DELAY_HORIZON_RAW_CAPTURE_RECORDED', 'candidate': 'price_delay_d1',
                        'request_sha256': a.expected_request_sha256, 'target_sha256': r['target_sha256'],
                        'legacy_helper_manifest_sha256': file_sha(out / 'manifest.json'),
                        'cleanup_sha256': file_sha(out / 'cleanup.json'),
                        'postcheck_sha256': file_sha(out / 'source-postcheck.json'),
                        'coordinate_reference_proofs_sha256': file_sha(out / 'coordinate-reference-proofs.json'),
                        'source_observation_reuse_not_packet_byte_copy': True, 'capture_complete': complete,
                        'source_admitted_for_account_replay': False, 'portfolio_returns_computed': False,
                        'investment_rules_changed': False, 'full_October_2026_complete': False, 'objective_achieved': False})
        finally:
            socket.setdefaulttimeout(previous_timeout)
    print('price-delay horizon raw capture complete', complete, 'no account/ROI', flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
