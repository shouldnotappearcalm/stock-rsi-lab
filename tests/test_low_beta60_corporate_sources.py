import copy
import unittest

try:
    from scripts.capture_low_beta60_corporate_sources import source_cases
except ImportError:
    source_cases = None
try:
    from scripts.continue_low_beta60_corporate_sources import select_implementation_notice
except ImportError:
    select_implementation_notice = None


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


class ImplementationTitleTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(select_implementation_notice)

    def test_original_profit_distribution_title_and_equity_distribution_both_work(self):
        case = {'instrument': 'SZ001914', 'publication_day': '2025-08-06'}
        for title in ('2024年度利润分配实施公告', '2024年年度权益分派实施公告'):
            row = {'code': '001914', 'day': '2025-08-06', 'title': title,
                   'announcement_id': '1224401972',
                   'pdf_path': 'finalpage/2025-08-06/1224401972.PDF'}
            self.assertEqual(select_implementation_notice([row], case), row)
            self.assertEqual(row['title'], title)

    def test_drafts_wrong_security_duplicates_and_wrong_pdf_paths_are_rejected(self):
        case = {'instrument': 'SZ001914', 'publication_day': '2025-08-06'}
        row = {'code': '001914', 'day': '2025-08-06', 'title': '2024年度利润分配实施公告',
               'announcement_id': '1224401972',
               'pdf_path': 'finalpage/2025-08-06/1224401972.PDF'}
        for change in ({'title': '2024年度利润分配预案'}, {'code': '002244'},
                       {'pdf_path': 'finalpage/2026-08-06/1224401972.PDF'}):
            with self.assertRaises(ValueError):
                select_implementation_notice([{**row, **change}], case)
        with self.assertRaises(ValueError):
            select_implementation_notice([row, dict(row)], case)
