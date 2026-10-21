"""Separately proven mixed cash/capital precision; no source or tax rewrite.

Callers authenticate the original row, PDF bytes and complete content review.
Half-unit consistency does not certify the provider's rounding algorithm.
Registry allocations and all existing account guards remain independent.
"""
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
import re

from stock_rsi.broker import money
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2
from stock_rsi.stock_distribution_account import StockDistributionAccount

CONTRACT = 'PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION_V1'
FIELDS = {'cash_per_share': 'dividCashPsBeforeTax', 'capital_per_share': 'dividReserveToStockPs'}


def positive(text):
    if not isinstance(text, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', text) or money(text) <= 0:
        raise ValueError('plain positive primary precision amount required')
    return money(text)


def apply_component_precision(events, receipts, packets, proofs, calendar):
    corrections = proofs.get('component_precision_overrides', {})
    if not isinstance(corrections, dict):
        raise ValueError('component precision proofs must be keyed by source event')
    if (len(events) != len(receipts) or len({e.event_id for e in events}) != len(events)
            or any(r['event_id'] != e.event_id or r['instrument'] != e.instrument
                   or r['ex_date'] != e.ex_date.isoformat() for e, r in zip(events, receipts))):
        raise ValueError('paired original event and receipt identities required')
    if not corrections:
        return tuple(events), tuple(receipts)
    if (proofs.get('component_precision_contract') != CONTRACT
            or set(corrections) & set(proofs.get('cash_overrides', {}))):
        raise ValueError('separate mixed precision contract without dual corrections required')
    documents = {d['file']: d for d in proofs['documents']}
    if len(documents) != len(proofs['documents']):
        raise ValueError('unique primary precision document required')
    rows = {}
    for code, packet in packets.items():
        for row in packet['distributions']:
            key = code + '|' + row['dividOperateDate']
            if key in rows:
                raise ValueError('duplicate vendor precision event')
            rows[key] = row
    consumed, result, evidence = set(), [], []
    for event, receipt in zip(events, receipts):
        key = event.instrument + '|' + event.ex_date.isoformat()
        proof = corrections.get(key)
        if proof is None:
            result.append(event)
            evidence.append(receipt)
            continue
        row, doc = rows.get(key), documents.get(proof['source_file'])
        if (row is None or doc is None or proof.get('verified') is not True
                or proof.get('kind') != 'PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION'
                or receipt['source_kind'] != 'VENDOR_DISTRIBUTION'
                or receipt['source_row_sha256'] != digest(row) or proof['source_row_sha256'] != digest(row)
                or doc['sha256'] != proof['source_sha256']
                or doc['instrument'] != event.instrument or doc['day'] != row['dividPlanDate']
                or event.announced.isoformat() != row['dividPlanDate']
                or event.stock_per_share != 0 or event.cash_per_share <= 0
                or money(row['dividStocksPs']) != 0
                or event.capital_per_share <= 0 or event.listed is None or event.pay_date is None
                or event.recorded.isoformat() != row['dividRegistDate']
                or event.pay_date.isoformat() != row['dividPayDate']
                or event.listed.isoformat() != row['dividStockMarketDate']
                or receipt['requires_zero_record_ownership_if_tax_unverified']
                   != (not event.capital_tax_exempt_verified)):
            raise ValueError('mixed precision proof must bind original vendor economics and primary identity')
        dates = {'record_date': 'dividRegistDate', 'ex_date': 'dividOperateDate',
                 'cash_payment_date': 'dividPayDate', 'stock_listing_date': 'dividStockMarketDate'}
        if (any(proof.get(k) != row[field] for k, field in dates.items())
                or not proof.get('primary_pages')
                or any(type(p) is not int or p < 1 for p in proof['primary_pages'])
                or set(proof['components']) != set(FIELDS)):
            raise ValueError('unchanged original dates, source pages and exactly cash/capital components required')
        # Reconstruct this single canonical vendor event. Paired caller values
        # alone cannot establish the original ID or authorize a tax flag.
        canonical_proofs = {**proofs, 'supplementary_distributions': [], 'cash_overrides': {}}
        for field in ('capital_tax', 'stock_dividend_tax_bases'):
            canonical_proofs[field] = {key: proofs[field][key]} if key in proofs.get(field, {}) else {}
        canonical_events, canonical_receipts = compile_distribution_events_v2(
            {event.instrument: {'instrument': event.instrument, 'distributions': [row]}},
            canonical_proofs, calendar)
        if canonical_events != (event,) or canonical_receipts != (receipt,):
            raise ValueError('original event and receipt differ from canonical vendor/proof compilation')
        changes, component_evidence = {}, {}
        for attribute, source_field in FIELDS.items():
            component, raw = proof['components'][attribute], row[source_field]
            if not isinstance(raw, str) or not re.fullmatch(r'[0-9]+\.[0-9]{6}', raw):
                raise ValueError('six-published-decimal original scalar required')
            expected = positive(component['expected_vendor_per_share'])
            effective = positive(component['effective_per_share'])
            per10 = positive(component['primary_per10_original_shares'])
            if (raw != component['expected_vendor_per_share'] or getattr(event, attribute) != expected
                    or effective == expected or Fraction(effective) != Fraction(per10) / 10
                    or abs(Fraction(effective) - Fraction(expected)) > Fraction(1, 2000000)):
                raise ValueError('primary per10 amount and exact six-decimal half-unit consistency required')
            changes[attribute] = effective
            component_evidence[attribute] = {'vendor_per_share': raw, 'effective_per_share': str(effective),
                                           'primary_per10_original_shares': str(per10)}
        proof_sha = digest(proof)
        identity = {'original_event_id': event.event_id, 'source_kind': 'PRIMARY_COMPONENT_PRECISION_CORRECTION',
                    'source_row_sha256': digest(row), 'primary_source_sha256': doc['sha256'],
                    'component_precision_proof_sha256': proof_sha, 'components': component_evidence}
        updated = replace(event, event_id=digest(identity), **changes)
        result.append(updated)
        evidence.append({**receipt, 'event_id': updated.event_id, 'original_event_id': event.event_id,
            'source_kind': identity['source_kind'], 'component_precision_proof_sha256': proof_sha,
            'precision_components': component_evidence,
            'primary_source_sha256': sorted(set(receipt['primary_source_sha256'] + [doc['sha256']]))})
        consumed.add(key)
    if consumed != set(corrections):
        raise ValueError('orphan component precision proof outside original vendor events')
    StockDistributionAccount(calendar, '1', result, tax_reserve_rate=Decimal('.2'))
    return tuple(result), tuple(evidence)


def compile_distribution_events_v3(packets, proofs, calendar):
    if set(proofs.get('component_precision_overrides', {})) & set(proofs.get('cash_overrides', {})):
        raise ValueError('one event cannot receive both precision contracts')
    events, receipts = compile_distribution_events_v2(packets, proofs, calendar)
    return apply_component_precision(events, receipts, packets, proofs, calendar)
