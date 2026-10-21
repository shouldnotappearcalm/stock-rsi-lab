import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

from scripts.illiquidity_scenario_tape import ScenarioTapeBank
from scripts.fundamental_query_journal import file_sha
from stock_rsi.archive_cent_clock import CONTRACT
from stock_rsi.data import digest


class FakeOriginalBank:
    def __init__(self, index, windows):
        self.index, self.windows, self.calls = index, windows, []

    def __call__(self, code, day):
        self.calls.append((code, day.isoformat()))
        return self.windows


class ScenarioTapeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.windows = [{'synthetic_bucket': i} for i in range(48)]
        self.old_key = ('SH600000', '2024-01-02')
        self.archive_key = ('SH603056', '2024-01-02')
        self.paths, records = {}, []
        for key in (self.old_key, self.archive_key):
            path = self.root / (key[0] + '-original.json')
            path.write_text('original source packet')
            self.paths[key] = (path, file_sha(path))
            records.append({'instrument': key[0], 'day': key[1], 'status': 'SOURCE_SCENARIO_COMPLETE',
                            'original_source_sha256': file_sha(path), 'window_digest': digest(self.windows),
                            'source_kind': 'UNCHANGED_ORIGINAL_TDX' if key == self.old_key else
                                'CONDITIONAL_ARCHIVE_CENT_CLOCK_INTERSECTION'})
        self.selected = self.root / (self.archive_key[0] + '-selected-development-rows.json')
        self.selected.write_text('original selected source bytes')
        self.projection = self.root / (self.archive_key[0] + '-' + self.archive_key[1] + '.json')
        self.projection.write_text(json.dumps({'contract': CONTRACT, 'instrument': self.archive_key[0],
            'day': self.archive_key[1], 'original_source_admission_overridden': False,
            'admitted_for_original_reconstructed_execution': False, 'windows': self.windows}))
        records[1].update(projection_file=self.projection.name, projection_sha256=file_sha(self.projection),
                          archive_selected_source_sha256=file_sha(self.selected))
        self.original = FakeOriginalBank(self.paths, self.windows)
        self.records = records
        self.bank = self.construct()

    def construct(self):
        return ScenarioTapeBank(self.original, self.records, self.root, self.root,
                                [self.old_key, self.archive_key], [self.archive_key])

    def call(self, key):
        return self.bank(key[0], date.fromisoformat(key[1]))

    def test_exact_source_routes_preserve_original_and_archive_windows(self):
        self.assertEqual(self.call(self.old_key), self.windows)
        self.assertEqual(self.call(self.archive_key), self.windows)
        self.assertEqual(self.original.calls, [self.old_key])
        self.assertEqual(self.bank.accessed, {self.old_key, self.archive_key})

    def test_cached_original_backing_mutation_is_rejected(self):
        self.call(self.old_key)
        self.paths[self.old_key][0].write_text('changed source')
        with self.assertRaisesRegex(ValueError, 'original backing bytes changed'):
            self.call(self.old_key)

    def test_cached_archive_projection_and_source_mutation_are_rejected(self):
        self.call(self.archive_key)
        original = self.projection.read_text()
        self.projection.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'archive projection changed'):
            self.call(self.archive_key)
        self.projection.write_text(original)
        self.selected.write_text('changed archive backing')
        with self.assertRaisesRegex(ValueError, 'archive backing bytes changed'):
            self.call(self.archive_key)

    def test_future_unknown_and_route_changes_fail_closed(self):
        for key in [('SH600000', '2026-01-05'), ('SH600000', '2024-01-03')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.call(key)
        self.records[0]['source_kind'] = 'CONDITIONAL_ARCHIVE_CENT_CLOCK_INTERSECTION'
        with self.assertRaisesRegex(ValueError, 'source route differs'):
            self.construct()

    def test_omitted_and_duplicate_sessions_are_rejected(self):
        original = self.records[:]
        for changed in [original[:1], original + original[:1]]:
            self.records = changed
            with self.assertRaisesRegex(ValueError, 'complete fixed source scenario scope'):
                self.construct()

    def test_cached_window_mutation_is_rejected_without_relabeling_source(self):
        self.call(self.archive_key)
        self.bank.cache[self.archive_key][0]['synthetic_bucket'] = 99
        with self.assertRaisesRegex(ValueError, 'window interpretation changed'):
            self.call(self.archive_key)


if __name__ == '__main__':
    unittest.main()
