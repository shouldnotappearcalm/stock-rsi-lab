import copy
import unittest

from stock_rsi import annual_profitability as annual
from stock_rsi import profitability_availability as availability
from stock_rsi.data import digest
from tests.test_industry_catalog import bundle
from tests.test_annual_profitability import pages


def document(year, day, key, sha='a' * 64):
    return {'effective_fiscal_year': year, 'day': day, 'capture_key': key,
            'instrument': 'SZ000998', 'source_sha256': sha, 'announcement_id': key,
            'captured_at_utc': '2026-10-22T00:00:00+00:00'}


def case(doc, status=availability.SUPPORTED):
    result = {'capture_key': doc['capture_key'], 'instrument': doc['instrument'],
              'fiscal_year': doc['effective_fiscal_year'], 'source_sha256': doc['source_sha256'],
              'status': status, 'source_observations': []}
    if status == availability.SUPPORTED:
        year = doc['effective_fiscal_year']
        cells = annual.parse_consolidated_tables(pages(year), year)[f'{year}-12-31']
        result['source_observations'] = [annual.make_observation(doc['instrument'], year,
            f'{year}-12-31', doc['day'], doc['captured_at_utc'], doc['source_sha256'], doc['announcement_id'], cells)]
    return result


class AvailabilityTests(unittest.TestCase):
    def snapshot(self, docs, cases, clock='2024-06-01T09:00:00+08:00', mode=annual.RECONSTRUCTED,
                 cohort=('SZ000998', 'SH600030', 'SH600001')):
        return availability.snapshot_availability(docs, cases.__getitem__, bundle(), list(cohort), clock, mode=mode)

    def test_default_observed_has_no_historical_values_or_case_reads(self):
        doc = document(2022, '2023-04-29', '1')
        snap = self.snapshot([doc], {}, mode=annual.OBSERVED)
        self.assertEqual(len(snap['classifications']), 3)
        self.assertTrue(all(r['annual_status'] == 'NO_VISIBLE_ANNUAL_REPORT' for r in snap['classifications']))

    def test_publication_day_end_and_hidden_future_payload_independence(self):
        old = document(2022, '2023-04-29', '1')
        future = {'day': '2025-04-29', 'captured_at_utc': '2026-10-22T00:00:00+00:00'}
        cases = {'1': case(old)}
        self.assertEqual(self.snapshot([old], cases), self.snapshot([old, future], cases))
        before = self.snapshot([old], {}, clock='2023-04-29T23:59:59.999998+08:00')
        self.assertTrue(all(r['annual_status'] == 'NO_VISIBLE_ANNUAL_REPORT' for r in before['classifications']))
        at = self.snapshot([old], cases, clock='2023-04-29T23:59:59.999999+08:00')
        self.assertEqual(at['classifications'][-1]['latest_fiscal_year'], 2022)

    def test_newer_unparsed_or_bad_identity_blocks_old_values(self):
        old, new = document(2022, '2023-04-29', '1'), document(2023, '2024-04-29', '2')
        for failed in availability.FAILURES:
            cases = {'1': case(old), '2': case(new, failed)}
            row = self.snapshot([old, new], cases)['classifications'][-1]
            self.assertEqual(row['annual_status'], 'LATEST_' + failed)
            self.assertNotIn('current_observation', row)

    def test_old_fiscal_reissue_does_not_replace_newer_fiscal_and_missing_cohort_survives(self):
        new, reissue = document(2023, '2024-04-29', '2'), document(2022, '2024-05-29', '3')
        snap = self.snapshot([new, reissue], {'2': case(new)})
        row = snap['classifications'][-1]
        self.assertEqual(row['selected_capture_key'], '2')
        self.assertEqual(row['industry_status'], 'NONFINANCIAL_IN_SOURCE_VINTAGE')
        self.assertFalse(row['investment_factor_admitted'])
        self.assertEqual(snap['classifications'][0]['industry_status'], 'NOT_IN_SOURCE_VINTAGE')
        self.assertEqual(snap['classifications'][1]['industry_status'], 'FINANCIAL_IN_SOURCE_VINTAGE')

    def test_same_day_conflict_retained_and_byte_identical_duplicates_have_fixed_witness(self):
        a, b = document(2023, '2024-04-29', '10'), document(2023, '2024-04-29', '2', 'b'*64)
        row = self.snapshot([a, b], {})['classifications'][-1]
        self.assertEqual(row['annual_status'], 'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS')
        b['source_sha256'] = a['source_sha256']
        row = self.snapshot([a, b], {'2': case(b)})['classifications'][-1]
        self.assertEqual(row['selected_capture_key'], '2')
        self.assertEqual(row['selected_edition_capture_keys'], ['2', '10'])

    def test_current_observation_only_and_source_payload_corruption_fails(self):
        doc = document(2023, '2024-04-29', '1')
        good = case(doc)
        for edit in [lambda c:c.update(source_sha256='b'*64),
                     lambda c:c.update(source_observations=[]),
                     lambda c:c['source_observations'][0]['payload'].update(column_role='COMPARATIVE'),
                     lambda c:c['source_observations'][0]['payload']['cells']['revenue'].update(value_CNY='99.00')]:
            broken = copy.deepcopy(good); edit(broken)
            with self.assertRaises(ValueError):self.snapshot([doc], {'1': broken})

    def test_no_2026_naive_clock_duplicate_cohort_or_unknown_mode(self):
        for kwargs in [{'clock':'2026-01-01T09:00:00+08:00'}, {'clock':'2024-01-01'},
                       {'cohort':('SZ000998','SZ000998')}, {'mode':'guess'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.snapshot([], {}, **kwargs)


if __name__ == '__main__':
    unittest.main()
