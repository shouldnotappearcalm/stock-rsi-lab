import csv
import importlib.util
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_published_strategy_2026_data as data
from scripts import run_published_strategies_2026 as run
from scripts.audit_published_strategies_2026 import independent_periods


class PublishedForwardTests(unittest.TestCase):
    def selection(self):
        return {'candidates': ['macd', 'rsi'], 'average_exposure_is_hard_gate': False, 'window': ['2024-01-02', '2026-10-27']}

    def development(self):
        return {'results': {'40/' + n: {'2024_return_pct': 1., '2025_return_pct': 1., 'average_exposure_pct': 1.} for n in ['macd', 'rsi']}}

    def test_low_exposure_does_not_block_the_two_human_selected_candidates(self):
        run.validate_selection(self.selection(), self.development())
        self.assertFalse(run.PROFILE['average_exposure_is_hard_gate'])
        self.assertEqual(run.PROFILE['candidates'], ['macd', 'rsi'])

    def test_neither_future_profit_nor_future_loss_changes_selection(self):
        for val in [-100., 1000.]:
            d = self.development()
            for m in d['results'].values(): m['2026_return_pct'] = val
            run.validate_selection(self.selection(), d)

    def test_reintroduced_exposure_gate_or_different_candidates_are_rejected(self):
        for changed in [{'average_exposure_is_hard_gate': True}, {'candidates': ['rsi']}, {'candidates': ['golden_cross', 'rsi']}]:
            with self.assertRaises(ValueError): run.validate_selection({**self.selection(), **changed}, self.development())
        d = self.development(); d['results']['40/macd']['2025_return_pct'] = 0
        with self.assertRaises(ValueError): run.validate_selection(self.selection(), d)

    def test_year2026_return_uses_december2025_nav_instead_of_original_cash(self):
        rows = [{'session': '2024-12-31', 'account_value': '1200000', 'stock_value': '600000', 'cost': '0', 'orders': '0'},
                {'session': '2025-12-31', 'account_value': '1500000', 'stock_value': '750000', 'cost': '0', 'orders': '0'},
                {'session': '2026-01-05', 'account_value': '1350000', 'stock_value': '675000', 'cost': '5', 'orders': '1'},
                {'session': '2026-10-27', 'account_value': '1650000', 'stock_value': '825000', 'cost': '5', 'orders': '1'}]
        periods = run.per_year(rows); separate = independent_periods(rows)
        self.assertEqual(periods['2026']['baseline_CNY'], 1500000)
        self.assertAlmostEqual(periods['2026']['net_return_pct'], 10)
        self.assertAlmostEqual(periods['2026']['max_drawdown_pct'], -10)
        self.assertEqual(periods['2026']['average_exposure_pct'], 50)
        for key, expected in separate['2026'].items(): self.assertAlmostEqual(periods['2026'][key], expected)

    def test_daily_slice_does_not_allow_nonfinite_or_reordered_nav(self):
        good = {'session': '2026-01-05', 'account_value': '1000000', 'stock_value': '0', 'cost': '0', 'orders': '0'}
        for changed in [{'account_value': 'nan'}, {'account_value': '0'}, {'cost': '-5'}]:
            with self.assertRaises(ValueError): run.per_year([{**good, **changed}])
        with self.assertRaises(ValueError): run.per_year([good, good])

    def test_existing_simulation_is_reused_only_end_date_changes_and_restores(self):
        original_end = run.base.END
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            with (p / 'days.csv').open('w') as f:
                w = csv.DictWriter(f, fieldnames=['session', 'account_value', 'stock_value', 'cost', 'orders']); w.writeheader()
                w.writerow({'session': '2026-01-05', 'account_value': 1000000, 'stock_value': 0, 'cost': 0, 'orders': 0})
            calls = []
            def simulate(provider, cfg, extra, out):
                calls.append((run.base.END, cfg.copy(), extra)); return {'unverified_held_marks': 0}
            cfg = {'id': 'macd', 'symbols': ['SZ000001']}
            with patch.object(run, 'strict_simulation', simulate): run.simulate(p, cfg, 40, p, '2026-10-27')
            self.assertEqual(calls, [('2026-10-27', cfg, 40)]); self.assertEqual(run.base.END, original_end)
            with patch.object(run, 'strict_simulation', side_effect=ValueError('source error')):
                with self.assertRaises(ValueError): run.simulate(p, cfg, 40, p, '2026-10-27')
            self.assertEqual(run.base.END, original_end)

    def test_prefix_comparison_detects_changed_historical_snapshots_or_csv(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / 'a', Path(t) / 'b'; a.mkdir(); b.mkdir()
            for p in [a, b]:
                for name in ['days.csv', 'orders.csv', 'holdings.csv']: (p / name).write_text('session,value\n2025-12-31,100\n')
                (p / 'decision_intents.json').write_text('[{"execution_session":"2025-12-31","snapshot_sha256":"same"}]')
            run.compare_prefix(a, b)
            (b / 'days.csv').write_text('session,value\n2025-12-31,101\n')
            with self.assertRaisesRegex(ValueError, 'days.csv'): run.compare_prefix(a, b)
            (b / 'days.csv').write_bytes((a / 'days.csv').read_bytes())
            (b / 'decision_intents.json').write_text('[{"execution_session":"2025-12-31","snapshot_sha256":"changed"}]')
            with self.assertRaisesRegex(ValueError, 'snapshots'): run.compare_prefix(a, b)

    def test_source_archive_checksum_is_enforced_before_extracting(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); archive = root / 'data.tar.gz'; archive.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'hash or size'): data.extract(archive, {'archive_size_bytes': 3, 'archive_sha256': 'sha256:wrong'}, root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_capped_views_use_real_next_session_and_do_not_copy_future_values(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); source = root / 'source'; (source / 'calendars').mkdir(parents=True); (source / 'instruments').mkdir()
            (source / 'calendars/day.txt').write_text('2025-12-31\n2026-01-05\n2026-10-27\n')
            (source / 'calendars/day_future.txt').write_text('2026-10-28\n2026-10-29\n')
            (source / 'instruments/all.txt').write_text(''.join(c + '\t2025-12-31\t2026-10-27\n' for c in data.CODES))
            for code in data.CODES:
                p = source / 'features' / code.lower(); p.mkdir(parents=True)
                for field in data.FIELDS: (p / (field + '.day.bin')).write_bytes(struct.pack('<4f', 0, 10, 11, 99999))
            pre = data.prepare_view(source, root / 'pre', '2025-12-31')
            full = data.prepare_view(source, root / 'full', '2026-10-27')
            self.assertEqual(pre['next_clock_session'], '2026-01-05'); self.assertEqual(full['next_clock_session'], '2026-10-28')
            for path in pre['per_feature']: self.assertEqual((root / 'pre' / path).read_bytes(), struct.pack('<2f', 0, 10))
            self.assertEqual((root / 'full/calendars/day_future.txt').read_text(), '2025-12-31\n2026-01-05\n2026-10-27\n2026-10-28\n')
            with self.assertRaisesRegex(ValueError, 'actual final'): data.prepare_view(source, root / 'invented', '2026-10-26')


if __name__ == '__main__': unittest.main()
