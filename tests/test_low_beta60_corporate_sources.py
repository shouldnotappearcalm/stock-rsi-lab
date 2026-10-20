import copy
import unittest

try:
    from scripts.capture_low_beta60_corporate_sources import source_cases
except ImportError:
    source_cases = None


class LowBeta60CorporateSourceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(source_cases)

    def fixture(self):
        dividend = {'code': 'sh.600001', 'dividOperateDate': '2024-06-07',
                    'dividCashPsBeforeTax': '.25', 'dividReserveToStockPs': '.29'}
        adjustment = {'code': 'sh.600002', 'dividOperateDate': '2024-07-15',
                      'adjustFactor': '1.5'}
        audit = {'noncash_distributions_requiring_review': [
            {'instrument': 'SH600001', 'record': dividend}],
            'adjustments_without_distribution': [['SH600002', '2024-07-15']]}
        packets = {'SH600001': {'distributions': [dividend], 'adjustments': []},
                   'SH600002': {'distributions': [], 'adjustments': [adjustment]}}
        return audit, packets

    def test_adjustment_generates_source_question_without_implying_entitlement(self):
        audit, packets = self.fixture()
        cases = source_cases(audit, packets)
        self.assertEqual(sorted(cases), ['SH600001|2024-06-07', 'SH600002|2024-07-15'])
        question = cases['SH600002|2024-07-15']
        self.assertEqual(question['kind'], 'ADJUSTMENT_WITHOUT_DISTRIBUTION')
        self.assertEqual(question['source_record']['adjustFactor'], '1.5')
        self.assertNotIn('dividCashPsBeforeTax', question['source_record'])
        self.assertNotIn('supplementary_distributions', question)

    def test_audit_distribution_or_adjustment_must_match_authenticated_packet(self):
        audit, packets = self.fixture()
        changed = copy.deepcopy(packets)
        changed['SH600001']['distributions'][0]['dividCashPsBeforeTax'] = '.5'
        with self.assertRaises(ValueError):
            source_cases(audit, changed)
        changed = copy.deepcopy(packets); changed['SH600002']['adjustments'] = []
        with self.assertRaises(ValueError):
            source_cases(audit, changed)

    def test_duplicate_or_post2025_cases_fail_instead_of_silently_overwriting(self):
        audit, packets = self.fixture()
        audit['adjustments_without_distribution'] *= 2
        with self.assertRaises(ValueError):
            source_cases(audit, packets)
        audit, packets = self.fixture()
        audit['adjustments_without_distribution'][0][1] = '2026-01-05'
        packets['SH600002']['adjustments'][0]['dividOperateDate'] = '2026-01-05'
        with self.assertRaises(ValueError):
            source_cases(audit, packets)
