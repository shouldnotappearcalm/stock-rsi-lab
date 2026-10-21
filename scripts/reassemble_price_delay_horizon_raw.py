"""Local-only assembly of one primary-backed source coordinate conflict."""
import argparse
import copy
import json
from pathlib import Path

from scripts import capture_price_delay_horizon_raw as frozen
from scripts.fundamental_query_journal import digest, file_sha, write_packet_once
from scripts.reassemble_value_momentum_raw_extension_v2 import (
    ReadOnlyJournal, expected_identities, tree_hashes, verify_coordinate_transition,
    verify_original_prefix,
)
from scripts.value_momentum_raw_extension_sources import fetch_packet, compose_packet

SOURCE = frozen.OUTPUT
PRIMARY = 'price-delay-horizon-missing-primary-20261021'
OUTPUT = 'price-delay-raw-horizon-v2-20261021'
REQUEST = 'experiments/qlib/price-delay-horizon-raw-source-request.json'
RAW_AUDIT = 'experiments/qlib/price-delay-horizon-raw-independent-audit.json'
CONTENT = 'experiments/qlib/price-delay-horizon-single-primary-content-review.json'
PRIMARY_AUDIT = 'experiments/qlib/price-delay-horizon-single-primary-independent-review.json'
PROTOCOL = 'docs/research/price-delay-horizon-local-reassembly-plan-2026-10-21.md'
METHODS = (*frozen.METHOD_FILES, 'scripts/reassemble_price_delay_horizon_raw.py')
PUBLIC = (REQUEST, RAW_AUDIT, CONTENT, PRIMARY_AUDIT, PROTOCOL,
    'experiments/qlib/audit_sources/2026-10-21-price-delay-horizon-raw-independent-audit.py',
    'experiments/qlib/audit_sources/2026-10-21-price-delay-horizon-single-primary-independent-review.py')
LOCAL = (SOURCE + '/manifest.json', SOURCE + '/price-delay-scope.json',
    PRIMARY + '/manifest.json')
PROFILE = {'status': 'FROZEN_PRICE_DELAY_LOCAL_RAW_REASSEMBLY_ONE_PRIMARY_COORDINATE',
    'candidate': 'price_delay_d1', 'window': [frozen.START, frozen.END],
    'copied_packets': 202, 'reassembled_codes': ['SH603233'], 'expected_names': 203,
    'output_directory': OUTPUT, 'maximum_new_source_queries': 0,
    'coordinate_rule': 'UNCHANGED_SIX_DECIMAL_HALF_UNIT_RATIONAL_INTERVAL',
    'investment_rules_changed': False, 'portfolio_returns_to_compute': False,
    'source_admitted_for_account_replay': False, 'full_October_complete': False}


def read(path):
    return json.loads(Path(path).read_bytes())


def forbidden_fetch(*args):
    raise ValueError('local-only assembly cannot request any new source')


def verify_source_capture_bindings(source, manifest, scope, audit, sessions):
    """Bind the new tree to the already audited canonical source identities."""
    for code, h in manifest['per_code_sha256'].items():
        if file_sha(frozen.safe(source, 'codes/' + code + '.json')) != h:
            raise ValueError('accepted packet differs from original audited manifest')
    for code, h in manifest['errors_sha256'].items():
        if file_sha(frozen.safe(source, 'errors/' + code + '.json')) != h:
            raise ValueError('original capture error bytes changed')
    if (file_sha(source / 'calendar.json') != manifest['calendar_sha256']
            or read(source / 'calendar.json')['sessions'] != sessions):
        raise ValueError('audited source calendar changed')
    for filename, key in (('cleanup.json', 'cleanup_sha256'), ('source-postcheck.json', 'postcheck_sha256'),
                          ('coordinate-reference-proofs.json', 'coordinate_reference_proofs_sha256')):
        if file_sha(source / filename) != scope[key]:
            raise ValueError('audited source cleanup/postcheck/proof bytes changed')
    recorded = audit['query_artifact_sha256']
    actual_names = {str(p.relative_to(source)) for p in (source / 'queries').rglob('*') if p.is_file()}
    if len(recorded) != 1035 or set(recorded) != actual_names:
        raise ValueError('exact audited1035 query artifact names required')
    for name, h in recorded.items():
        if file_sha(frozen.safe(source, name)) != h:
            raise ValueError('query bytes differ from prior independent source audit')


def make_conflict_packet(journal, request_sha, baseline, sessions, reference, review):
    source = fetch_packet(journal, 'SH603233', request_sha, forbidden_fetch, baseline)
    proof = verify_coordinate_transition(source, reference, review)
    result = compose_packet('SH603233', source, baseline, sessions)
    verify_original_prefix(result, baseline)
    result['source_query_receipts'] = copy.deepcopy(source['source_query_receipts'])
    return result, proof


def authenticate(path, expected, repo, base):
    if file_sha(path) != expected:
        raise ValueError('local reassembly request SHA changed')
    r = read(path)
    if (any(type(r.get(k)) is not type(v) or r[k] != v for k, v in PROFILE.items())
            or set(r['method_code_sha256']) != set(METHODS)
            or set(r['public_evidence_sha256']) != set(PUBLIC)
            or set(r['local_source_sha256']) != set(LOCAL)):
        raise ValueError('fixed202copies/oneconflict/zeroquery protocol required')
    for field, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo),
                        ('local_source_sha256', base)):
        for name, h in r[field].items():
            if file_sha(frozen.safe(root, name)) != h:
                raise ValueError('frozen reassembly method/evidence/source changed')
    context = frozen.authenticate_request(repo / REQUEST, r['original_request_sha256'], repo, base)
    original, codes, sessions, baselines, cached, overlaps, lineage, existing_proofs = context
    source = base / SOURCE
    if (tree_hashes(source) != r['immutable_capture_tree_sha256']
            or tree_hashes(base / PRIMARY) != r['immutable_primary_tree_sha256']
            or (source / 'request.json').read_bytes() != (repo / REQUEST).read_bytes()
            or frozen.immutable_financial_hashes(base) != r['immutable_financial_sha256']):
        raise ValueError('original failed source tree or financial files changed')
    m, scope, audit = read(source / 'manifest.json'), read(source / 'price-delay-scope.json'), read(repo / RAW_AUDIT)
    if (set(m['errors_sha256']) != {'SH603233'} or m['pending_codes'] or m['abnormal_exit'] is not None
            or set(m['per_code_sha256']) != set(codes) - {'SH603233'} or m['names'] != 202
            or m['requested_names'] != 203 or m['query_reservations_consumed'] != 345
            or m['maximum_source_reservations'] != 345 or scope['capture_complete'] is not False
            or audit['capture_manifest_sha256'] != file_sha(source / 'manifest.json')
            or audit['scope_sha256'] != file_sha(source / 'price-delay-scope.json')
            or audit['request_sha256'] != r['original_request_sha256']
            or audit['audit_code_sha256'] != file_sha(repo / PUBLIC[5])
            or audit['failed_capture_correctly_preserved'] is not True
            or audit['imports_project_code'] is not False
            or audit['saved_packets_independently_reconstructed'] != 202
            or audit['fresh_component_chains_reconstructed'] != 345
            or audit['original48_financial_artifacts_unchanged'] is not True
            or audit['critical_or_important_audit_findings']):
        raise ValueError('independently authenticated preserved failed capture required')
    verify_source_capture_bindings(source, m, scope, audit, sessions)
    identities = expected_identities(codes, baselines, cached, r['original_request_sha256'])
    if len(identities) != 345 or {digest(x) for x in identities} != {x.name for x in (source / 'queries').iterdir()}:
        raise ValueError('exact original345 saved query identities required')
    journal = ReadOnlyJournal(source)
    for identity in identities:
        journal.query(identity)
    pm, content, pa = read(base / PRIMARY / 'manifest.json'), read(repo / CONTENT), read(repo / PRIMARY_AUDIT)
    if (pm['capture_complete'] is not True or pm['errors'] or pm['http_query_reservations'] != 1
            or content['capture_manifest_sha256'] != file_sha(base / PRIMARY / 'manifest.json')
            or content['all_pages_text_extracted_and_visually_reviewed'] is not True
            or content['documents_read'] != 1 or content['pages_read'] != 4
            or pa['capture_manifest_sha256'] != file_sha(base / PRIMARY / 'manifest.json')
            or pa['root_content_review_sha256'] != file_sha(repo / CONTENT)
            or pa['audit_code_sha256'] != file_sha(repo / PUBLIC[6])
            or pa['imports_project_code'] is not False
            or pa['all4pages_independently_text_extracted_and_visually_reviewed'] is not True
            or pa['critical'] or pa['important']):
        raise ValueError('complete independently reviewed original four-page primary required')
    doc, review = pm['documents']['SH603233'], content['documents'][0]
    if (review['instrument'] != 'SH603233' or review['sha256'] != doc['sha256']
            or file_sha(frozen.safe(base / PRIMARY, doc['file'])) != doc['sha256']
            or review['cash_per_original_share_CNY'] != '0.41'
            or review['stock_per_original_share'] != '0' or review['capital_per_original_share'] != '0'):
        raise ValueError('exact primary cash-only identity required')
    for kind in ('request', 'reserved', 'response'):
        receipt = doc['pdf_receipt']
        if file_sha(frozen.safe(base / PRIMARY, receipt[kind + '_file'])) != receipt[kind + '_sha256']:
            raise ValueError('primary response receipt bytes changed')
    route = original['cache_routes']['SH603233']
    if route['cache_route'] != frozen.SOURCES[2] or route['source_class'] != 'incremental':
        raise ValueError('specific old derived-baseline cache route required')
    reference = read(base / route['cache_route'] / 'codes/SH603233.json')
    packet, proof = make_conflict_packet(journal, r['original_request_sha256'], baselines['SH603233'], sessions, reference, review)
    if digest(proof) != r['new_coordinate_proof_sha256']:
        raise ValueError('exact new primary-backed coordinate proof changed')
    return r, codes, sessions, baselines, packet, proof


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ('request', 'expected-request-sha256', 'source-root', 'output-dir'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--preflight-only', action='store_true')
    a = p.parse_args(argv)
    repo, base, out = Path(__file__).resolve().parents[1], Path(a.source_root), Path(a.output_dir)
    if out.exists() or out.resolve() != (base / OUTPUT).resolve():
        raise ValueError('fixed unused reassembly output required; preserve prior data')
    r, codes, sessions, baselines, packet, proof = authenticate(a.request, a.expected_request_sha256, repo, base)
    if a.preflight_only:
        print('203 local source identities;202copies+oneexactcoordinateproof;zero network/output/ROI', flush=True)
        return 0
    source = base / SOURCE
    out.mkdir(parents=True)
    (out / 'codes').mkdir()
    (out / 'request.json').write_bytes(Path(a.request).read_bytes())
    (out / 'calendar.json').write_bytes((source / 'calendar.json').read_bytes())
    copied = {}
    for code in codes:
        if code == 'SH603233':
            continue
        path = source / 'codes' / (code + '.json')
        copied[code] = read(source / 'manifest.json')['per_code_sha256'][code]
        (out / 'codes' / path.name).write_bytes(path.read_bytes())
    packet['provenance'] = {'kind': 'LOCAL_ONLY_PRICE_DELAY_PRIMARY_COORDINATE_ASSEMBLY',
        'request_sha256': a.expected_request_sha256,
        'original_failed_capture_manifest_sha256': file_sha(source / 'manifest.json'),
        'original_query_receipts_relative_to': SOURCE,
        'source_query_receipts': packet['source_query_receipts'],
        'baseline_provenance': copy.deepcopy(baselines['SH603233'].get('provenance')),
        'baseline_source_route': read(repo / REQUEST)['cache_routes']['SH603233'],
        'primary_notice_sha256': proof['primary_notice']['sha256'],
        'factor_values_normalized_or_rewritten': False, 'vendor_dividend_rows_supplemented': False}
    write_packet_once(out / 'codes/SH603233.json', packet)
    write_packet_once(out / 'new-coordinate-proof.json', proof)
    # Reauthenticate every immutable input before allowing a completion record.
    authenticate(a.request, a.expected_request_sha256, repo, base)
    hashes = {c: file_sha(out / 'codes' / (c + '.json')) for c in codes}
    if any(hashes[c] != h for c, h in copied.items()):
        raise ValueError('copied source packet bytes changed')
    totals = {k: sum(len(read(out / 'codes' / (c + '.json'))[k]) for c in codes)
              for k in ('bars', 'distributions', 'adjustments', 'quarantine')}
    write_packet_once(out / 'manifest.json', {'status': 'PRICE_DELAY_203_LOCAL_RAW_REASSEMBLY_INDEPENDENT_ADMISSION_PENDING',
        'request_sha256': a.expected_request_sha256, 'target_sha256': read(repo / REQUEST)['target_sha256'],
        'window': PROFILE['window'], 'names': 203, 'calendar_sha256': file_sha(out / 'calendar.json'),
        'per_code_sha256': hashes, 'copied_packet_sha256': copied,
        'reassembled_codes': ['SH603233'], 'totals': totals,
        'new_coordinate_proof_sha256': file_sha(out / 'new-coordinate-proof.json'),
        'original_failed_capture_manifest_sha256': file_sha(source / 'manifest.json'),
        'original_query_receipts_relative_to': SOURCE, 'original_query_reservations_consumed': 345,
        'primary_manifest_sha256': file_sha(base / PRIMARY / 'manifest.json'),
        'all_original_capture_bytes_unchanged': True, 'all48_financial_artifacts_unchanged': True,
        'local_assembly_complete': True, 'new_source_queries': 0,
        'factor_values_rewritten': False, 'vendor_cash_rows_supplemented': False,
        'source_admitted_for_account_replay': False, 'historical_arrival_verified': False,
        'portfolio_returns_computed': False, 'investment_rules_changed': False,
        'full_October_2026_complete': False, 'objective_achieved': False})
    print('203names local-only assembly; original failed capture unchanged; noROI/admission', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
