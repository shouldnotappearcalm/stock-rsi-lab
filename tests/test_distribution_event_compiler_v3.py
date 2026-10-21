import copy
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal as D

from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2
from stock_rsi.stock_distribution_account import StockDistributionAccount
try:
    from stock_rsi import distribution_event_compiler_v3 as api
except ImportError:
    api = None


class MixedComponentPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(api)
        self.code = 'SZ000001'  # Synthetic issuer, not a market-data fixture.
        self.key = self.code + '|2025-08-13'
        self.cal = TradingCalendar(['2025-08-11', '2025-08-12', '2025-08-13', '2025-08-14'])
        self.row = {'code': 'sz.000001', 'dividPlanDate': '2025-08-06',
            'dividRegistDate': '2025-08-12', 'dividOperateDate': '2025-08-13',
            'dividPayDate': '2025-08-13', 'dividStockMarketDate': '2025-08-13',
            'dividCashPsBeforeTax': '0.123457', 'dividStocksPs': '0',
            'dividReserveToStockPs': '0.234568', 'dividCashStock': '10转2.345683派1.234567元'}
        self.packets = {self.code: {'instrument': self.code, 'distributions': [self.row]}}
        self.proof = {'verified': True, 'kind': 'PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION',
            'source_file': 'notice.pdf', 'source_sha256': 'a' * 64, 'source_row_sha256': digest(self.row),
            'record_date': '2025-08-12', 'ex_date': '2025-08-13',
            'cash_payment_date': '2025-08-13', 'stock_listing_date': '2025-08-13', 'primary_pages': [1, 2],
            'components': {
                'cash_per_share': {'expected_vendor_per_share': '0.123457',
                    'primary_per10_original_shares': '1.234567', 'effective_per_share': '0.1234567'},
                'capital_per_share': {'expected_vendor_per_share': '0.234568',
                    'primary_per10_original_shares': '2.345683', 'effective_per_share': '0.2345683'}}}
        self.proofs = {'documents': [{'file': 'notice.pdf', 'sha256': 'a' * 64,
            'instrument': self.code, 'day': '2025-08-06'}], 'capital_tax': {},
            'stock_dividend_tax_bases': {}, 'supplementary_distributions': [],
            'component_precision_contract': api.CONTRACT,
            'component_precision_overrides': {self.key: self.proof}}

    def compile(self):
        return api.compile_distribution_events_v3(self.packets, self.proofs, self.cal)

    def test_mixed_decrease_and_increase_keep_source_tax_dates_and_inputs_unchanged(self):
        before = copy.deepcopy((self.packets, self.proofs))
        old, old_receipts = compile_distribution_events_v2(self.packets, self.proofs, self.cal)
        events, receipts = self.compile()
        self.assertEqual(events[0].cash_per_share, D('0.1234567'))
        self.assertEqual(events[0].capital_per_share, D('0.2345683'))
        self.assertFalse(events[0].capital_tax_exempt_verified)
        self.assertEqual(receipts[0]['requires_zero_record_ownership_if_tax_unverified'], True)
        self.assertEqual((events[0].announced, events[0].recorded, events[0].ex_date, events[0].pay_date, events[0].listed),
                         (old[0].announced, old[0].recorded, old[0].ex_date, old[0].pay_date, old[0].listed))
        self.assertEqual(receipts[0]['source_row_sha256'], old_receipts[0]['source_row_sha256'])
        self.assertEqual(receipts[0]['original_event_id'], old[0].event_id)
        self.assertEqual(receipts[0]['source_kind'], 'PRIMARY_COMPONENT_PRECISION_CORRECTION')
        self.assertEqual((self.packets, self.proofs), before)
        self.assertEqual(self.compile(), (events, receipts))

    def test_no_correction_is_exactly_the_original_v2_output(self):
        self.proofs['component_precision_overrides'] = {}
        self.assertEqual(self.compile(), compile_distribution_events_v2(self.packets, self.proofs, self.cal))

    def test_apply_rejects_coherent_forged_original_identity_or_tax_flags(self):
        events, receipts = compile_distribution_events_v2(self.packets, self.proofs, self.cal)
        changed = copy.deepcopy(receipts)
        changed[0]['requires_zero_record_ownership_if_tax_unverified'] = False
        with self.assertRaises(ValueError):
            api.apply_component_precision((replace(events[0], capital_tax_exempt_verified=True),),
                                          changed, self.packets, self.proofs, self.cal)
        changed = copy.deepcopy(receipts)
        changed[0]['event_id'] = 'coherently-forged'
        with self.assertRaises(ValueError):
            api.apply_component_precision((replace(events[0], event_id='coherently-forged'),),
                                          changed, self.packets, self.proofs, self.cal)

    def test_wrong_row_document_dates_pages_units_and_interval_fail(self):
        original = copy.deepcopy((self.packets, self.proofs))
        changes = [('source_row_sha256', 'b' * 64), ('source_sha256', 'b' * 64),
            ('record_date', '2025-08-11'), ('ex_date', '2025-08-14'),
            ('stock_listing_date', '2025-08-14'), ('cash_payment_date', None),
            ('primary_pages', []), ('primary_pages', [True]), ('verified', False)]
        for field, value in changes:
            self.packets, self.proofs = copy.deepcopy(original)
            self.proofs['component_precision_overrides'][self.key][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.compile()
        for field, value in [('expected_vendor_per_share', '0.123458'),
                ('primary_per10_original_shares', '1.234568'), ('effective_per_share', '0.1234559'),
                ('effective_per_share', 'NaN'), ('effective_per_share', '-0.1234567'),
                ('effective_per_share', '0'), ('effective_per_share', '0.123457')]:
            self.packets, self.proofs = copy.deepcopy(original)
            self.proofs['component_precision_overrides'][self.key]['components']['cash_per_share'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.compile()

    def test_orphan_duplicate_unsupported_component_and_dual_contract_are_rejected(self):
        original = copy.deepcopy(self.proofs)
        self.proofs['component_precision_overrides'][self.code + '|2025-08-14'] = copy.deepcopy(self.proof)
        with self.assertRaises(ValueError):
            self.compile()
        self.proofs = copy.deepcopy(original)
        self.proofs['component_precision_overrides'][self.key]['components']['stock_per_share'] = {}
        with self.assertRaises(ValueError):
            self.compile()
        self.proofs = copy.deepcopy(original)
        self.proofs['cash_overrides'] = {self.key: {}}
        with self.assertRaises(ValueError):
            self.compile()
        self.proofs = copy.deepcopy(original)
        self.packets[self.code]['distributions'].append(copy.deepcopy(self.row))
        with self.assertRaises(ValueError):
            self.compile()

    def test_verified_tax_still_cannot_bypass_fractional_registry_guard(self):
        self.proofs['capital_tax'][self.key] = {'source_file': 'notice.pdf',
            'source_sha256': 'a' * 64, 'verified_exempt': True}
        events, _ = self.compile()
        a = StockDistributionAccount(self.cal, '1000', events, tax_reserve_rate='.2')
        a.broker.positions = {self.code: [{'quantity': 100, 'price': D('1'), 'bought_on': date(2025, 8, 11)}]}
        a.end_day(date(2025, 8, 12))
        before = copy.deepcopy((a.broker.cash, a.broker.positions, a.corporate_ledger, a.cash_claims, a.stock_claims))
        with self.assertRaises(ValueError):
            a.start_day(date(2025, 8, 13))
        self.assertEqual((a.broker.cash, a.broker.positions, a.corporate_ledger, a.cash_claims, a.stock_claims), before)
