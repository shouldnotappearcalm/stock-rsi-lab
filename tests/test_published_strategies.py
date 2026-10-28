import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from stock_rsi import published_signals as signals
from scripts.prepare_published_strategy_data import prepare

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'experiments/published-strategies'


class PublishedSignalsTests(unittest.TestCase):
    def test_original_commit_object_and_file_blobs_authenticate(self):
        manifest = json.loads((SOURCES / 'source-manifest.json').read_text())
        data = (SOURCES / 'upstream/commit.txt').read_bytes()
        self.assertEqual(hashlib.sha1(b'commit ' + str(len(data)).encode() + b'\0' + data).hexdigest(), manifest['snapshot_commit'])
        self.assertLess(manifest['snapshot_committer_at'], '2024-01-01')
        self.assertLess(manifest['snapshot_author_at'], '2024-01-01')
        self.assertEqual(len(manifest['strategies']), 3)
        for row in manifest['strategies']:
            raw = (SOURCES / 'upstream' / (row['strategy'] + '.py')).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
            self.assertEqual(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(), row['blob_sha1'])
        self.assertEqual(hashlib.sha256((SOURCES / 'upstream/LICENSE').read_bytes()).hexdigest(), manifest['license_sha256'])

    def test_skill_numeric_parameters_and_symbols_equal_original_literals(self):
        expected = {'golden_cross': {'SHORTPERIOD': 20, 'LONGPERIOD': 120},
                    'macd': {'SHORTPERIOD': 12, 'LONGPERIOD': 26, 'SMOOTHPERIOD': 9, 'OBSERVATION': 100},
                    'rsi': {'TIME_PERIOD': 14, 'HIGH_RSI': 85, 'LOW_RSI': 30, 'ORDER_PERCENT': .3}}
        for name, values in expected.items():
            tree = ast.parse((SOURCES / 'upstream' / (name + '.py')).read_text())
            literals = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Attribute) and isinstance(node.value, ast.Constant):
                    literals[node.targets[0].attr] = node.value.value
            self.assertEqual({k: literals[k] for k in values}, values)
            config = json.loads((ROOT / 'skills' / ('a-share-published-' + name.replace('_', '-')) / 'skill.json').read_text())
            self.assertEqual(config['symbols'], ['SZ000001', 'SH601988', 'SZ000068'] if name == 'rsi' else ['SZ000001'])
            self.assertEqual(config['source_blob_sha256'], hashlib.sha256((SOURCES / 'upstream' / (name + '.py')).read_bytes()).hexdigest())
        rsi = json.loads((ROOT / 'skills/a-share-published-rsi/skill.json').read_text())
        self.assertEqual((rsi['period'], rsi['low'], rsi['high'], rsi['cash_fraction'], rsi['history']), (14, 30, 85, .3, 15))

    def test_strict_cross_has_no_equal_or_level_trigger(self):
        for pair in [(0, 1), (-1, 0), (1, 0), (0, -1), (1, 2), (-2, -1)]:
            self.assertEqual(signals.cross(*pair), 'HOLD')
        self.assertEqual(signals.cross(-1, 1), 'BUY')
        self.assertEqual(signals.cross(1, -1), 'SELL')

    def test_golden_cross_uses_previous_and_current_windows(self):
        self.assertEqual(signals.golden_cross([10] * 100 + [9] * 20 + [50])['action'], 'BUY')
        self.assertEqual(signals.golden_cross([10] * 100 + [10.1] * 20 + [1])['action'], 'SELL')
        self.assertEqual(signals.golden_cross([10] * 121)['action'], 'HOLD')

    def test_macd_and_rsi_match_external_talib_reference_vectors(self):
        reference = json.loads((SOURCES / 'indicator-reference.json').read_text())
        self.assertFalse(reference['contains_market_data'])
        for row in reference['fixture_vectors']:
            actual = signals.macd_histogram(row['closes'])
            self.assertEqual(len(actual), len(row['histogram']))
            for a, b in zip(actual, row['histogram']): self.assertAlmostEqual(a, b, places=12)
            self.assertAlmostEqual(signals.rsi(row['closes'][-15:])['rsi'], row['rsi_last15'], places=12)

    def test_rsi_original_15_observations_not_long_wilder_recursion(self):
        self.assertEqual(signals.rsi(list(range(1, 16)))['rsi'], 100)
        self.assertEqual(signals.rsi(list(range(16, 1, -1)))['rsi'], 0)
        self.assertEqual(signals.rsi([10] * 15)['rsi'], 0)
        for up, down, expected in [(3, 7, 30), (17, 3, 85)]:
            seq = [100]
            for change in [up] * 7 + [-down] * 7: seq.append(seq[-1] + change)
            value = signals.rsi(seq)
            self.assertEqual(value['rsi'], expected); self.assertEqual(value['action'], 'HOLD')

    def test_incomplete_nonfinite_or_extra_history_fails_closed(self):
        for history in [[10] * 14, [10] * 16, [10] * 14 + [float('nan')], [10] * 14 + [0]]:
            with self.assertRaises(ValueError): signals.rsi(history)
        with self.assertRaises(ValueError): signals.evaluate('optimized_variant', [10] * 121)

    def test_all_development_criteria_are_required(self):
        ok = {'2024_return_pct': 1., '2025_return_pct': 1., 'average_exposure_pct': 90., 'unverified_held_marks': 0}
        self.assertTrue(signals.admission(ok))
        for key, value in [('2024_return_pct', 0), ('2025_return_pct', -1), ('average_exposure_pct', 89.99), ('unverified_held_marks', 1)]:
            self.assertFalse(signals.admission({**ok, key: value}))
        with self.assertRaises(ValueError): signals.admission({**ok, '2024_return_pct': float('nan')})

    def test_provider_does_not_invent_final_session(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); (root / 'source/calendars').mkdir(parents=True)
            (root / 'source/calendars/day.txt').write_text('2025-12-30\n2026-01-05\n')
            with self.assertRaisesRegex(ValueError, 'actual final'): prepare(root / 'source', root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_prefix_preparer_never_copies_future_quote_tail(self):
        import struct
        from scripts.prepare_published_strategy_data import CODES, FIELDS
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); source = root / 'source'; (source / 'calendars').mkdir(parents=True); (source / 'instruments').mkdir()
            (source / 'calendars/day.txt').write_text('2025-12-30\n2025-12-31\n2026-01-05\n')
            (source / 'instruments/all.txt').write_text(''.join(c + '\t2025-12-30\t2026-01-05\n' for c in CODES))
            for code in CODES:
                folder = source / 'features' / code.lower(); folder.mkdir(parents=True)
                for field in FIELDS: (folder / (field + '.day.bin')).write_bytes(struct.pack('<4f', 0, 10, 11, 999999))
            result = prepare(source, root / 'out')
            for relative in result['per_feature']:
                self.assertEqual((root / 'out' / relative).read_bytes(), struct.pack('<3f', 0, 10, 11))
            self.assertFalse(result['2026_quote_values_read'])


class PublishedRunBoundaryTests(unittest.TestCase):
    def request(self):
        return {'configs': {name: {'id': name} for name in signals.NAMES}}

    def test_all_failed_candidates_leave_2026_uncomputed(self):
        from scripts import run_published_strategies as runner
        metric = {'2024_return_pct': -1., '2025_return_pct': 20., 'average_exposure_pct': 95., 'unverified_held_marks': 0}
        with tempfile.TemporaryDirectory() as t, patch.object(runner, 'verify', return_value=self.request()), patch.object(runner, 'simulate', return_value=metric) as sim:
            result = runner.run(ROOT, Path(t), Path(t) / 'request', 'fixed', Path(t) / 'out')
            self.assertEqual(sim.call_count, 6)
            self.assertEqual(result['passed_development_screen'], [])
            self.assertIsNone(result['2026_return_pct']); self.assertFalse(result['2026_values_read'])
            self.assertEqual(result['next_step'], 'REJECT_ALL_THREE_NO2026_ACCESS')

    def test_screen_pass_is_not_raw_qualification_or_forward_permission(self):
        from scripts import run_published_strategies as runner
        metric = {'2024_return_pct': 1., '2025_return_pct': 1., 'average_exposure_pct': 95., 'unverified_held_marks': 0}
        with tempfile.TemporaryDirectory() as t, patch.object(runner, 'verify', return_value=self.request()), patch.object(runner, 'simulate', return_value=metric):
            result = runner.run(ROOT, Path(t), Path(t) / 'request', 'fixed', Path(t) / 'out')
            self.assertEqual(result['passed_development_screen'], list(signals.NAMES))
            self.assertFalse(result['investment_admitted']); self.assertFalse(result['2026_values_read'])
            self.assertEqual(result['next_step'], 'RAW_ACCOUNT_AND_SOURCE_QA_BEFORE_ANY2026')

    def test_simulation_error_preserves_terminal_without_partial_success(self):
        from scripts import run_published_strategies as runner
        with tempfile.TemporaryDirectory() as t, patch.object(runner, 'verify', return_value=self.request()), patch.object(runner, 'simulate', side_effect=ValueError('missing source')):
            out = Path(t) / 'out'
            with self.assertRaisesRegex(ValueError, 'missing source'): runner.run(ROOT, Path(t), Path(t) / 'request', 'fixed', out)
            value = json.loads((out / 'terminal.json').read_text())
            self.assertFalse(value['complete']); self.assertIsNone(value['2026_return_pct'])
            self.assertNotIn('passed_development_screen', value)

    def test_input_change_quarantines_even_positive_returns(self):
        from scripts import run_published_strategies as runner
        metric = {'2024_return_pct': 1., '2025_return_pct': 1., 'average_exposure_pct': 95., 'unverified_held_marks': 0}
        with tempfile.TemporaryDirectory() as t, patch.object(runner, 'verify', side_effect=[self.request(), ValueError('changed')]), patch.object(runner, 'simulate', return_value=metric):
            out = Path(t) / 'out'
            with self.assertRaisesRegex(ValueError, 'quarantined'): runner.run(ROOT, Path(t), Path(t) / 'request', 'fixed', out)
            value = json.loads((out / 'terminal.json').read_text())
            self.assertFalse(value['complete']); self.assertEqual(value['results'], {})
            self.assertEqual(value['passed_development_screen'], [])


@unittest.skipUnless(importlib.util.find_spec('qlib'), 'optional Qlib research dependency unavailable')
class PublishedAccountDecisionTests(unittest.TestCase):
    def test_rsi_cash_is_sequential_not_fixed_equity_weights_or_sale_proceeds(self):
        from stock_rsi.published_qlib_strategy import plan_orders
        config = {'id': 'rsi', 'symbols': ['A', 'B', 'C']}
        rows = {c: {'action': 'BUY'} for c in config['symbols']}
        result = plan_orders(config, rows, 100000, 100000, {}, {c: 10 for c in rows}, {c: 1 for c in rows})
        self.assertEqual([x['normalized_units'] for x in result], [3000, 2100, 1400])
        rows['A'] = {'action': 'SELL'}
        result = plan_orders(config, rows, 100000, 10000, {'A': 9000}, {c: 10 for c in rows}, {c: 1 for c in rows})
        self.assertEqual([(x['side'], x['normalized_units']) for x in result], [('SELL', 9000), ('BUY', 300), ('BUY', 200)])

    def test_no_signal_means_no_forced_high_exposure(self):
        from stock_rsi.published_qlib_strategy import plan_orders
        self.assertEqual(plan_orders({'id': 'macd', 'symbols': ['A']}, {'A': {'action': 'HOLD'}}, 100000, 100000, {}, {'A': 10}, {'A': 1}), [])

    def test_source_decision_is_unchanged_by_future_prices_and_exchange(self):
        import pandas as pd
        from datetime import date, timedelta
        from qlib.backtest.position import Position
        from stock_rsi.published_qlib_strategy import PublishedPriorCloseStrategy
        dates = tuple(date(2023, 1, 1) + timedelta(days=x) for x in range(122))
        observations = [10] * 100 + [9] * 20 + [50]
        class Snapshot:
            calendar = dates
            calls = []
            future = 100
            def value(self, symbol, field, day):
                at = date.fromisoformat(day); self.calls.append(at)
                if at > dates[-2]: raise AssertionError('future field decoded')
                return observations[dates.index(at)] if field == 'close' else 1.
        class Forbidden:
            def __getattr__(self, key): raise AssertionError('exchange read during decision')
        snap = Snapshot(); strategy = PublishedPriorCloseStrategy(config={'id': 'golden_cross', 'history': 121, 'symbols': ['A']}, snapshot=snap)
        strategy.common_infra = SimpleNamespace(get=lambda key: SimpleNamespace(current_position=Position(cash=100000)))
        strategy.level_infra = SimpleNamespace(get=lambda key: SimpleNamespace(get_step_time=lambda: (pd.Timestamp(dates[-1]), pd.Timestamp(dates[-1]))))
        strategy._trade_exchange = Forbidden()
        before = [(x.stock_id, x.amount) for x in strategy.generate_trade_decision().get_decision()]
        snap.future = 999999
        after = [(x.stock_id, x.amount) for x in strategy.generate_trade_decision().get_decision()]
        self.assertEqual(before, after); self.assertEqual(before, [('A', 1900.)])
        self.assertLessEqual(max(snap.calls), dates[-2])


if __name__ == '__main__': unittest.main()
