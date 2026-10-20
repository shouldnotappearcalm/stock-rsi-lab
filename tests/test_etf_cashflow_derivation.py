import hashlib
import unittest
from test_etf_action_sources import html
try:
    from scripts.derive_etf_cashflows_pre2026 import extract_typed_cashflows
except ImportError:
    extract_typed_cashflows=None


class ETFCashflowDerivationTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(extract_typed_cashflows)

    def test_per_ten_units_are_explicitly_divided_and_original_byte_provenance_is_retained(self):
        row='<tr><td>2025年</td><td>2025-06-17</td><td>2025-06-18</td><td>每10份派现金0.8800元</td><td>2025-06-27</td></tr>'
        raw=html(row).replace('每份分红'.encode(),'每10份分红'.encode());before=bytes(raw)
        result=extract_typed_cashflows(raw,'SH510300')
        self.assertEqual(result['dividends'][0]['cash_per_unit'],'0.0880')
        self.assertEqual(result['dividends'][0]['cash_provider_raw'],'每10份派现金0.8800元')
        self.assertEqual(result['dividends'][0]['cash_provider_denominator'],10)
        self.assertEqual(result['original_html_sha256'],hashlib.sha256(before).hexdigest());self.assertEqual(raw,before)
        self.assertFalse(result['primary_event_truth_certified'])

    def test_future_amounts_stay_uninterpreted_even_when_header_requires_conversion(self):
        row='<tr><td>2026年</td><td>not interpreted</td><td>2026-01-15</td><td>bad future units and amount</td><td>not interpreted</td></tr>'
        raw=html(row).replace('每份分红'.encode(),'每10份分红'.encode())
        result=extract_typed_cashflows(raw,'SH510300')
        self.assertEqual(result['dividends'],[]);self.assertEqual(result['outside_window_rows_excluded'],1)
        self.assertNotIn('bad future',str(result));self.assertFalse(result['provider_asserts_no_dividends'])

    def test_mixed_or_unstated_unit_does_not_silently_turn_into_per_unit_cash(self):
        row='<tr><td>2025年</td><td>2025-06-17</td><td>2025-06-18</td><td>每份派现金0.8800元</td><td>2025-06-27</td></tr>'
        raw=html(row).replace('每份分红'.encode(),'每10份分红'.encode())
        with self.assertRaisesRegex(ValueError,'unit'):extract_typed_cashflows(raw,'SH510300')
        with self.assertRaises(ValueError):extract_typed_cashflows(html().replace('每份分红'.encode(),'每10份分红'.encode()),'SH510300')

    def test_original_per_unit_and_explicit_none_semantics_are_preserved(self):
        row='<tr><td>2025年</td><td>2025-06-17</td><td>2025-06-18</td><td>每份派现金0.0880元</td><td>2025-06-27</td></tr>'
        result=extract_typed_cashflows(html(row),'SH510300');self.assertEqual(result['dividends'][0]['cash_per_unit'],'0.0880')
        empty=html('<tr><td colspan="5">暂无分红信息!</td></tr>').replace('每份分红'.encode(),'每10份分红'.encode())
        result=extract_typed_cashflows(empty,'SH510300');self.assertTrue(result['provider_asserts_no_dividends'])
        self.assertEqual(result['dividends'],[])
