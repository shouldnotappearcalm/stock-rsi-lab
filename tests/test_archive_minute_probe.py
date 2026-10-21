import copy
from datetime import datetime
from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest

from stock_rsi.archive_minute_probe import compare_session, selected_parquet_rows, validate_pairs


class ArchiveMinuteProbeTests(unittest.TestCase):
    def fixture(self):
        day = '2024-01-02'
        labels = [f'{h:02d}:{m:02d}' for h in (9,10,11,13,14,15) for m in range(60)
                  if '09:31' <= f'{h:02d}:{m:02d}' <= '11:30'
                  or '13:01' <= f'{h:02d}:{m:02d}' <= '15:00']
        rows = [dict(symbol='603056', exchange='SH', timestamp=datetime.fromisoformat(day+'T'+t),
                     open=10., high=10., low=10., close=10., volume=100, turnover=1000.) for t in labels]
        daily = dict(date=day, tradestatus='1', open='10', high='10', low='10', close='10', volume='24000')
        return day, rows, daily

    def test_exact_numeric_match_still_does_not_admit_an_execution_source(self):
        day, rows, daily = self.fixture();before = copy.deepcopy(rows)
        r = compare_session('SH603056',day,rows,daily)
        self.assertTrue(r['all_numeric_and_existing_label_checks_pass'])
        self.assertFalse(r['admitted_for_reconstructed_execution'])
        self.assertFalse(r['upstream_providers_independently_authenticated'])
        self.assertEqual(before,rows)

    def test_extra_opening_label_is_reported_without_shifting_or_deleting_it(self):
        day, rows, daily = self.fixture()
        first=copy.deepcopy(rows[0]);first['timestamp']=datetime.fromisoformat(day+'T09:30');first['volume']=0
        rows.insert(0,first);r=compare_session('SH603056',day,rows,daily)
        self.assertEqual(r['rows'],241)
        self.assertEqual(r['first_label'],'09:30')
        self.assertFalse(r['source_checks']['exact_existing_240_end_labels'])
        self.assertTrue(r['source_checks']['total_volume_matches'])

    def test_floating_near_cent_prices_and_volume_mismatch_are_not_repaired(self):
        day, rows, daily = self.fixture()
        rows[0].update(open=9.999999,low=9.999999,volume=101)
        r=compare_session('SH603056',day,rows,daily)
        self.assertFalse(r['source_checks']['first_open_matches'])
        self.assertFalse(r['source_checks']['all_prices_exact_cent_without_rounding'])
        self.assertFalse(r['source_checks']['total_volume_matches'])

    def test_identity_duplicates_outside_session_and_nonfinite_values_fail(self):
        for mutate in [lambda r:r[0].update(symbol='000001'), lambda r:r.append(copy.deepcopy(r[-1])),
                       lambda r:r[0].update(timestamp=datetime(2024,1,2,12)),
                       lambda r:r[0].update(high=float('nan')),lambda r:r[0].update(volume=True)]:
            day,rows,daily=self.fixture();mutate(rows)
            with self.assertRaises(ValueError):compare_session('SH603056',day,rows,daily)

    def test_future_unsorted_or_unregistered_requests_fail_before_reader_import(self):
        for pairs in [[['SH603056','2026-01-05']], [['SH600000','2024-01-02']],
                      [['SZ002505','2024-03-01'],['SH603056','2024-01-02']],
                      [['SH603056','2024-01-02']]*2]:
            with self.assertRaises(ValueError):selected_parquet_rows('nonexistent',pairs)
        validate_pairs([['SH603056','2024-01-02'],['SZ002505','2024-03-01']])

    @unittest.skipUnless(find_spec('pyarrow'), 'optional parquet integration dependency')
    def test_parquet_filter_exposes_only_exact_development_sessions_and_future_values_cannot_change_facts(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        day,rows,daily=self.fixture();future=copy.deepcopy(rows[0]);future['timestamp']=datetime(2026,1,5,9,31)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'mixed.parquet';pq.write_table(pa.Table.from_pylist(rows+[future]),path,row_group_size=300)
            picked=selected_parquet_rows(path,[['SH603056',day]])
            first=compare_session('SH603056',day,picked,daily)
            self.assertEqual(len(picked),240)
            future.update(open=99999.,high=99999.,low=99999.,close=99999.,volume=9999999)
            pq.write_table(pa.Table.from_pylist(rows+[future]),path,row_group_size=300)
            picked=selected_parquet_rows(path,[['SH603056',day]])
            self.assertEqual(first,compare_session('SH603056',day,picked,daily))


if __name__=='__main__':unittest.main()
