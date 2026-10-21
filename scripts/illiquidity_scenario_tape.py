"""Account-facing adapter for a separately authenticated source scenario.

Construct only after authenticating the frozen source request and all34 output
artifacts. This adapter itself grants neither source nor account admission.
"""
from datetime import date
import json
from pathlib import Path

from scripts.fundamental_query_journal import file_sha
from stock_rsi.archive_cent_clock import CONTRACT
from stock_rsi.archive_minute_probe import need
from stock_rsi.data import digest


class ScenarioTapeBank:
    def __init__(self, original_bank, records, scenario_dir, archive_dir,
                 expected_active, expected_rejected):
        self.original = original_bank
        self.scenario_dir = Path(scenario_dir)
        self.archive_dir = Path(archive_dir)
        self.records = {(r['instrument'], r['day']): r for r in records}
        need(len(self.records) == len(records) and set(self.records) == set(map(tuple, expected_active)),
             'complete fixed source scenario scope required')
        self.rejected = set(map(tuple, expected_rejected))
        need(self.rejected <= set(self.records), 'archive route outside original scope')
        self.accessed, self.cache = set(), {}
        for key, row in self.records.items():
            need(row['status'] == 'SOURCE_SCENARIO_COMPLETE', 'incomplete source scenario')
            expected_kind = ('CONDITIONAL_ARCHIVE_CENT_CLOCK_INTERSECTION' if key in self.rejected
                             else 'UNCHANGED_ORIGINAL_TDX')
            need(row['source_kind'] == expected_kind, 'source route differs from original failure set')
            if key in self.rejected:
                need(row['projection_file'] == key[0] + '-' + key[1] + '.json', 'unsafe scenario filename')

    def __call__(self, code, day):
        need(type(day) is date and '2024-01-01' <= day.isoformat() <= '2025-12-31',
             'pre2026 development tape access required')
        key = (code, day.isoformat())
        self.accessed.add(key)
        need(key in self.records, 'tape access outside frozen complete prefix')
        record = self.records[key]
        original_path, expected = self.original.index[key]
        need(expected == record['original_source_sha256'] and file_sha(original_path) == expected,
             'original backing bytes changed, including cached access')
        if key in self.rejected:
            path = self.scenario_dir / record['projection_file']
            need(file_sha(path) == record['projection_sha256'], 'archive projection changed, including cached access')
            # Hash the unmodified selected source even if decoded windows are cached.
            # The complete selected-file SHA must be attached by the authenticated loader.
            source = self.archive_dir / (code + '-selected-development-rows.json')
            need(file_sha(source) == record['archive_selected_source_sha256'],
                 'archive backing bytes changed, including cached access')
            if key not in self.cache:
                value = json.loads(path.read_text())
                need(value['contract'] == CONTRACT and value['instrument'] == code and value['day'] == key[1]
                     and value['original_source_admission_overridden'] is False
                     and value['admitted_for_original_reconstructed_execution'] is False,
                     'conditional source identity or scope changed')
                self.cache[key] = value['windows']
            windows = self.cache[key]
        else:
            windows = self.original(code, day)
        need(len(windows) == 48 and digest(windows) == record['window_digest'],
             'frozen complete window interpretation changed')
        return windows
