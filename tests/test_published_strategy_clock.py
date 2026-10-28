import json
from pathlib import Path
import tempfile
import unittest
from scripts.prepare_published_strategy_clock import prepare
from scripts.run_published_strategies_clock import validate_clock
from scripts.prepare_published_strategy_data import sha


class PublishedClockTests(unittest.TestCase):
    def setup_source(self, root):
        source = root / 'v1'; (source / 'calendars').mkdir(parents=True)
        (source / 'calendars/day.txt').write_text('2025-12-30\n2025-12-31\n')
        (source / 'calendars/day_future.txt').write_text('2025-12-30\n2025-12-31\n')
        (source / 'quotes.bin').write_bytes(b'old quote bytes')
        hashes = {str(p.relative_to(source)): sha(p) for p in source.rglob('*') if p.is_file()}
        (source / 'manifest.json').write_text(json.dumps({'all_output_sha256': hashes}))
        calendar = root / 'actual-calendar.txt'; calendar.write_text('2025-12-30\n2025-12-31\n2026-01-05\n2026-01-06\n')
        return source, calendar

    def test_clock_only_repair_preserves_all_quote_and_day_calendar_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); source, calendar = self.setup_source(root); out = root / 'v2'
            before = {str(p.relative_to(source)): sha(p) for p in source.rglob('*') if p.is_file()}
            prepare(source, calendar, out); validate_clock(out)
            self.assertEqual((out / 'calendars/day_future.txt').read_text(), '2025-12-30\n2025-12-31\n2026-01-05\n')
            self.assertEqual((out / 'quotes.bin').read_bytes(), (source / 'quotes.bin').read_bytes())
            self.assertEqual((out / 'calendars/day.txt').read_bytes(), (source / 'calendars/day.txt').read_bytes())
            self.assertEqual(before, {str(p.relative_to(source)): sha(p) for p in source.rglob('*') if p.is_file()})
            (out / 'quotes.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'quote'): validate_clock(out)

    def test_no_weekday_inference_or_replaced_source_prefix(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); source, calendar = self.setup_source(root)
            calendar.write_text('2025-12-29\n2025-12-31\n2026-01-05\n')
            with self.assertRaisesRegex(ValueError, 'unchanged'): prepare(source, calendar, root / 'v2')
            self.assertFalse((root / 'v2').exists())
