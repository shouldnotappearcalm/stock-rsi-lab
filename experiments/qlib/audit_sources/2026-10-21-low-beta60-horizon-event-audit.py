"""Stdlib incremental reconstruction: trusted prior266 plus three source cash events."""
import argparse
import copy
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_bytes())
digest = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def verify_increment(old, prior, events, receipts, added, added_receipts):
    assert len(old) == len(prior) and len(added) == len(added_receipts)
    assert events == old + added and receipts == prior + added_receipts
    assert [e['event_id'] for e in events] == [r['event_id'] for r in receipts]
    assert len(events) == len({e['event_id'] for e in events})


def audit(base, repo, out, planfile, expected_plan_sha):
    assert sha(planfile) == expected_plan_sha
    plan, summary = read(planfile), read(out / 'summary.json')
    assert summary['plan_sha256'] == expected_plan_sha
    for field, parent in (('method_code_sha256', repo), ('local_source_sha256', base), ('public_evidence_sha256', repo)):
        for name, h in plan[field].items(): assert sha(parent / name) == h
    for name, h in summary['artifact_sha256'].items(): assert sha(out / name) == h
    previous = base / 'low-beta60-account-source-events-2026-20261021'
    previous_audit = read(base / 'low-beta60-extension-event-independent-audit-20261021.json')
    assert previous_audit['summary_sha256'] == sha(previous / 'summary.json')
    for name, h in read(previous / 'summary.json')['artifact_sha256'].items(): assert sha(previous / name) == h
    old, prior = read(previous / 'derived_events.json'), read(previous / 'event_source_receipts.json')
    assert len(old) == len(prior) == 266
    for name in ('derived_events.json', 'event_source_receipts.json'):
        assert (out / ('prior_' + name)).read_bytes() == (previous / name).read_bytes()
    proofdir = base / 'low-beta60-corporate-reviewed-horizon-20261021'
    proofs, original_proofs = read(proofdir / 'reviewed-manifest.json'), read(previous / 'effective_2026_proofs.json')
    assert (out / 'effective_horizon_proofs.json').read_bytes() == (proofdir / 'reviewed-manifest.json').read_bytes()
    for key in ('capital_tax', 'stock_dividend_tax_bases', 'cash_overrides', 'unresolved_tax'):
        assert proofs[key] == original_proofs[key]
    assert proofs['documents'][:6] == original_proofs['documents'] and len(proofs['documents']) == 7
    assert proofs['supplementary_distributions'][:1] == original_proofs['supplementary_distributions']
    assert len(proofs['supplementary_distributions']) == 2
    for d in proofs['documents']: assert sha(proofdir / d['file']) == d['sha256']
    raw = base / 'low-beta60-raw-horizon-20261021'; manifest = read(raw / 'manifest.json')
    sessions = read(raw / 'calendar.json')['sessions']; assert len(sessions) == 676 and sessions[-1] == '2026-10-20'
    assert summary['raw_manifest_sha256'] == proofs['raw_manifest_sha256'] == sha(raw / 'manifest.json')
    assert summary['proof_manifest_sha256'] == sha(proofdir / 'reviewed-manifest.json')
    assert read(base / 'low-beta60-horizon-independent-audit-20261021.json')['manifest_sha256'] == sha(raw / 'manifest.json')
    packets = {}
    for code, h in manifest['per_code_sha256'].items():
        f = raw / 'codes' / (code + '.json'); assert sha(f) == h; packets[code] = read(f)
        assert [r['date'] for r in packets[code]['bars']] == sessions and not packets[code]['quarantine']
    added, added_receipts = [], []
    facts = [('SH600398', '2026-10-13', '2026-10-14', '0.27'), ('SH600312', '2026-10-14', '2026-10-15', '0.242'), ('SH601598', '2026-10-19', '2026-10-20', '0.14')]
    for code, recorded, ex, amount in facts:
        primary = []
        if code == 'SH601598':
            supplement = proofs['supplementary_distributions'][1]; assert supplement['instrument'] == code
            row = supplement['record']; kind = 'PRIMARY_NOTICE_SUPPLEMENT'
            doc = next(d for d in proofs['documents'] if d['file'] == supplement['source_file'])
            assert doc['sha256'] == supplement['source_sha256'] == '6c23f8c2d99a0f6feed5800f3f02571f6575aa6d17f9dcee739ed20d140f2c4a'
            assert doc['instrument'] == code and doc['day'] == row['dividPlanDate'] == '2026-10-13'
            primary = [doc['sha256']]
            assert not any(r['dividOperateDate'] == ex for r in packets[code]['distributions'])
        else:
            rows = [r for r in packets[code]['distributions'] if r['dividOperateDate'] == ex]
            assert len(rows) == 1; row = rows[0]; kind = 'VENDOR_DISTRIBUTION'
        assert row['code'] == code[:2].lower() + '.' + code[2:]
        assert row['dividRegistDate'] == recorded and row['dividOperateDate'] == row['dividPayDate'] == ex
        assert row['dividCashPsBeforeTax'] == amount and Decimal(row['dividStocksPs']) == 0
        assert not row['dividStockMarketDate'] and row['dividReserveToStockPs'] in ('', '0')
        if not row['dividReserveToStockPs']:
            assert row['dividCashStock'].startswith('10派') and '送' not in row['dividCashStock'] and '转' not in row['dividCashStock']
        identity = {'instrument': code, 'source_kind': kind, 'source_distribution': row, 'primary_source_sha256': primary,
            'effective_stock_taxable_income_per_original_share': '0', 'capital_tax_exempt_verified': False, 'stock_tax_basis_verified': False}
        event_id = digest(identity)
        added.append({'event_id': event_id, 'instrument': code, 'announced': row['dividPlanDate'], 'recorded': recorded,
            'ex_date': ex, 'pay_date': ex, 'listed': None, 'cash_per_share': amount, 'capital_per_share': '0',
            'capital_tax_exempt_verified': False, 'stock_per_share': str(Decimal(row['dividStocksPs'])),
            'stock_taxable_income_per_share': '0', 'stock_tax_basis_verified': False})
        added_receipts.append({'event_id': event_id, 'instrument': code, 'ex_date': ex, 'source_kind': kind,
            'source_row_sha256': digest(row), 'primary_source_sha256': primary,
            'blank_capital_resolved_as_zero': not bool(row['dividReserveToStockPs']), 'requires_zero_record_ownership_if_tax_unverified': False})
    events, receipts = read(out / 'derived_events.json'), read(out / 'event_source_receipts.json')
    verify_increment(old, prior, events, receipts, added, added_receipts)
    assert len(events) == 269 and summary['compiled_events'] == 269
    assert summary['preserved_prior_events'] == 266 and summary['new_post_Oct13_events'] == 3
    assert summary['source_kind_counts'] == dict(Counter(r['source_kind'] for r in receipts)) == {'VENDOR_DISTRIBUTION': 264, 'PRIMARY_NOTICE_SUPPLEMENT': 3, 'PRIMARY_CASH_PRECISION_CORRECTION': 2}
    unknown = [r['instrument'] + '|' + r['ex_date'] for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']]
    assert unknown == ['SZ000937|2026-06-17'] and summary['unverified_tax_event_keys'] == unknown
    oldnames = set(read(base / 'low-beta60-raw-dev-20261021/manifest.json')['per_code_sha256'])
    targets = read(base / 'low-beta60-calendar-extension-formations-20261021/targets.json')['low_beta60']
    assert {c for day, t in targets.items() if day < '2026-01-01' for c in t['weights']} == oldnames
    for code, packet in packets.items():
        bars = packet['bars'] if code in oldnames else [r for r in packet['bars'] if r['date'] >= '2025-12-31']
        exdates = {e['ex_date'] for e in events if e['instrument'] == code}
        previous_close = None; indices = {r['date']: i for i, r in enumerate(bars)}
        for r in bars:
            if previous_close is not None and r['preclose'] and Decimal(r['preclose']) > 0:
                assert abs(Decimal(r['preclose']) - previous_close) <= Decimal('.005') or r['date'] in exdates
            if r['close'] and Decimal(r['close']) > 0: previous_close = Decimal(r['close'])
        for r in packet['adjustments']:
            day = r['dividOperateDate']
            if code not in oldnames and day < '2026-01-01': continue
            assert day in indices; i = indices[day]
            assert day in exdates or i > 0 and bars[i - 1]['date'] in exdates
    negative = {}
    for label in ('old_cash_rewrite', 'new_cash_rewrite', 'missing_primary', 'wrong_record_day', 'erased_tax_guard'):
        changed_events, changed_receipts = copy.deepcopy(events), copy.deepcopy(receipts)
        if label == 'old_cash_rewrite': changed_events[0]['cash_per_share'] = '999'
        elif label == 'new_cash_rewrite': changed_events[-1]['cash_per_share'] = '999'
        elif label == 'missing_primary': changed_events.pop(); changed_receipts.pop()
        elif label == 'wrong_record_day': changed_events[-1]['recorded'] = '2026-10-20'
        else:
            index = next(i for i, r in enumerate(changed_receipts) if r['requires_zero_record_ownership_if_tax_unverified'])
            changed_receipts[index]['requires_zero_record_ownership_if_tax_unverified'] = False
        try: verify_increment(old, prior, changed_events, changed_receipts, added, added_receipts)
        except AssertionError: negative[label] = True
        else: raise AssertionError('semantic mutation accepted')
    assert summary['account_replay_admitted'] is False and summary['portfolio_returns_computed'] is False
    return {'status': 'INDEPENDENT269_EVENTS_PRIOR266_LITERAL_PREFIX_AND_THREE_CASH_APPENDS_VERIFIED',
        'audit_code_sha256': sha(__file__), 'plan_sha256': expected_plan_sha, 'summary_sha256': sha(out / 'summary.json'),
        'verified_events': 269, 'preserved_prior_events': 266, 'new_cash_events': added,
        'full2026_reference_and_adjustment_coverage': True, 'source_kind_counts': summary['source_kind_counts'],
        'unverified_tax_event_keys': unknown, 'semantic_negative_controls_rejected': negative,
        'capture_bound_deviation_retained': proofs['protocol_deviation'], 'source_queries': 0,
        'account_replay_admitted': False, 'portfolio_returns_computed': False, 'full_October_complete': False, 'objective_achieved': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'repo-root', 'event-dir', 'plan', 'expected-plan-sha256', 'output'): parser.add_argument('--' + name, required=True)
    a = parser.parse_args(); result = audit(Path(a.source_root), Path(a.repo_root), Path(a.event_dir), Path(a.plan), a.expected_plan_sha256)
    with Path(a.output).open('x') as f: json.dump(result, f, ensure_ascii=False, indent=2); f.write('\n')
    print('independently verified269 events, prior266 prefix and three cash appends; noROI')
