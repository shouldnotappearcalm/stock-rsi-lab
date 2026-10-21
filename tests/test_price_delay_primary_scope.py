import copy
import unittest

from scripts.capture_price_delay_corporate_sources_pre2026 import source_cases


class PriceDelayPrimaryScopeTests(unittest.TestCase):
    def fixture(self):
        distribution = {'dividOperateDate': '2024-05-20', 'dividReserveToStockPs': '.4'}
        adjustment = {'dividOperateDate': '2024-07-15', 'adjustFactor': '1.1'}
        questions = {'noncash': [{'instrument': 'SH603596', 'record': distribution}],
                     'unknown_economics': [],
                     'adjustments_without_distribution': [{'instrument': 'SH603596', 'record': adjustment}]}
        packet = {'distributions': [copy.deepcopy(distribution)], 'adjustments': [copy.deepcopy(adjustment)]}
        return {'questions': questions}, {'SH603596': packet}

    def test_exact_source_questions_preserve_rows_and_no_inferred_entitlement(self):
        audit, packets = self.fixture(); before = copy.deepcopy((audit, packets))
        cases = source_cases(audit, packets)
        self.assertEqual(cases['SH603596|2024-07-15']['kind'], 'ADJUSTMENT_WITHOUT_DISTRIBUTION')
        self.assertEqual(cases['SH603596|2024-07-15']['source_record'], packets['SH603596']['adjustments'][0])
        self.assertEqual((audit, packets), before)

    def test_adjustment_row_tampering_rejected_even_if_issuer_and_day_match(self):
        audit, packets = self.fixture()
        audit['questions']['adjustments_without_distribution'][0]['record']['adjustFactor'] = '2.0'
        with self.assertRaises(ValueError): source_cases(audit, packets)

    def test_unresolved_components_and_future_dates_are_not_silently_skipped(self):
        audit, packets = self.fixture(); audit['questions']['unknown_economics'] = ['unresolved']
        with self.assertRaises(ValueError): source_cases(audit, packets)
        audit, packets = self.fixture()
        audit['questions']['noncash'][0]['record']['dividOperateDate'] = '2026-01-05'
        packets['SH603596']['distributions'][0]['dividOperateDate'] = '2026-01-05'
        with self.assertRaises(ValueError): source_cases(audit, packets)
