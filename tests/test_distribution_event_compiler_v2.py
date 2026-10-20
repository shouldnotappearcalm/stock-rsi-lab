import copy
import unittest
from datetime import date
from decimal import Decimal as D

from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.stock_distribution_account import StockDistributionAccount
try:
    from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2
except ImportError:
    compile_distribution_events_v2 = None


class PrimaryCashPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(compile_distribution_events_v2)
        self.cal = TradingCalendar(['2025-08-11', '2025-08-12', '2025-08-13', '2025-08-14'])
        self.row = {'code': 'sz.001914', 'dividPlanDate': '2025-08-06',
            'dividRegistDate': '2025-08-12', 'dividOperateDate': '2025-08-13',
            'dividPayDate': '2025-08-13', 'dividStockMarketDate': '',
            'dividCashPsBeforeTax': '0.240097', 'dividStocksPs': '0',
            'dividReserveToStockPs': '', 'dividCashStock': '10派2.400974元'}
        self.packets = {'SZ001914': {'instrument': 'SZ001914', 'distributions': [self.row]}}
        self.correction = {'verified': True, 'kind': 'PRIMARY_NOTICE_CASH_PRECISION',
            'source_row_sha256': digest(self.row), 'expected_vendor_cash_per_share': '0.240097',
            'effective_cash_per_share': '0.2400974', 'source_file': 'notice.pdf',
            'source_sha256': 'a'*64}
        self.proofs = {'documents': [{'file': 'notice.pdf', 'sha256': 'a'*64,
            'instrument': 'SZ001914', 'day': '2025-08-06'}], 'capital_tax': {},
            'stock_dividend_tax_bases': {}, 'supplementary_distributions': [],
            'cash_override_contract': 'PRIMARY_NOTICE_CASH_PRECISION_V1',
            'cash_overrides': {'SZ001914|2025-08-13': self.correction}}

    def compile(self):
        return compile_distribution_events_v2(self.packets, self.proofs, self.cal)

    def test_effective_cash_and_receipt_keep_original_vendor_and_primary_identity(self):
        before = copy.deepcopy((self.packets, self.proofs))
        events, receipts = self.compile()
        self.assertEqual(events[0].cash_per_share, D('0.2400974'))
        self.assertEqual((self.packets, self.proofs), before)
        r = receipts[0]
        self.assertEqual(r['source_kind'], 'PRIMARY_CASH_PRECISION_CORRECTION')
        self.assertEqual(r['source_row_sha256'], digest(self.row))
        self.assertEqual(r['vendor_cash_per_share'], '0.240097')
        self.assertEqual(r['effective_cash_per_share'], '0.2400974')
        self.assertEqual(r['primary_source_sha256'], ['a'*64])
        self.assertEqual(r['cash_precision_proof_sha256'], digest(self.correction))
        self.assertEqual(events[0].event_id, self.compile()[0][0].event_id)

    def test_hand_computed_cash_is_paid_after_pay_day_without_creating_duplicate_event(self):
        events, _ = self.compile()
        a = StockDistributionAccount(self.cal, '1', events, tax_reserve_rate='0')
        a.broker.positions = {'SZ001914': [{'quantity': 100000, 'price': D('1'),
                                          'bought_on': date(2025, 8, 11)}]}
        a.end_day(date(2025, 8, 12)); a.start_day(date(2025, 8, 13))
        self.assertEqual(a.broker.cash, D('1'))
        self.assertEqual(a.cash_claims[0]['gross'], D('24009.74'))
        a.start_day(date(2025, 8, 14)); a.start_day(date(2025, 8, 14))
        self.assertEqual(a.broker.cash, D('24010.74'))
        self.assertEqual(len(a.cash_claims), 1)

    def test_legacy_compiler_still_rejects_new_contract_and_uncorrected_outputs_are_identical(self):
        with self.assertRaises(ValueError):
            compile_distribution_events(self.packets, self.proofs, self.cal)
        self.proofs['cash_overrides'] = {}
        self.assertEqual(self.compile(), compile_distribution_events(self.packets, self.proofs, self.cal))

    def test_row_document_security_and_announcement_tampering_are_rejected(self):
        original = copy.deepcopy((self.packets, self.proofs))
        for mutation in ('row', 'row_sha', 'pdf_sha', 'security', 'announcement'):
            self.packets, self.proofs = copy.deepcopy(original)
            p = self.proofs['cash_overrides']['SZ001914|2025-08-13']
            if mutation == 'row': self.packets['SZ001914']['distributions'][0]['dividPayDate'] = '2025-08-14'
            elif mutation == 'row_sha': p['source_row_sha256'] = 'b'*64
            elif mutation == 'pdf_sha': p['source_sha256'] = 'b'*64
            elif mutation == 'security': self.proofs['documents'][0]['instrument'] = 'SZ002244'
            else: self.proofs['documents'][0]['day'] = '2025-08-05'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.compile()

    def test_not_a_precision_completion_nonfinite_stock_or_wrong_contract_is_rejected(self):
        original = copy.deepcopy((self.packets, self.proofs))
        for value in ('0.2397745', '0.2400984', '0.240097', 'NaN', 'Infinity', '-0.2400974'):
            self.packets, self.proofs = copy.deepcopy(original)
            self.proofs['cash_overrides']['SZ001914|2025-08-13']['effective_cash_per_share'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): self.compile()
        self.packets, self.proofs = copy.deepcopy(original)
        row = self.packets['SZ001914']['distributions'][0]
        row.update(dividStocksPs='0.4', dividReserveToStockPs='0', dividStockMarketDate='2025-08-13')
        self.proofs['cash_overrides']['SZ001914|2025-08-13']['source_row_sha256'] = digest(row)
        with self.assertRaises(ValueError): self.compile()
        self.packets, self.proofs = copy.deepcopy(original)
        self.proofs['cash_override_contract'] = 'unknown'
        with self.assertRaises(ValueError): self.compile()

    def test_orphan_and_duplicate_source_rows_fail_without_mutation(self):
        before = copy.deepcopy((self.packets, self.proofs))
        self.proofs['cash_overrides']['SZ001914|2025-08-14'] = copy.deepcopy(self.correction)
        with self.assertRaises(ValueError): self.compile()
        self.packets, self.proofs = copy.deepcopy(before)
        self.packets['SZ001914']['distributions'].append(copy.deepcopy(self.row))
        snapshot = copy.deepcopy((self.packets, self.proofs))
        with self.assertRaises(ValueError): self.compile()
        self.assertEqual((self.packets, self.proofs), snapshot)
