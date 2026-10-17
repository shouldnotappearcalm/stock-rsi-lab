"""Synthetic exchange sessions verify calendar boundaries and halted returns."""
import math
from datetime import date
import unittest

try:
    from stock_rsi.lottery_max import calendar_max_score, build_targets
except ImportError:
    calendar_max_score = build_targets = None


class LotteryMaxTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(calendar_max_score, 'calendar MAX implementation missing')

    def test_max_is_single_daily_return_not_monthly_return_and_sign_is_low_first(self):
        self.assertAlmostEqual(calendar_max_score([100., 110., 99.], [1., 1.]), -.1)
        self.assertAlmostEqual(calendar_max_score([100., 99., 98.], [1., 1.]), .01)
        self.assertGreater(calendar_max_score([100., 99., 98.], [1., 1.]),
                           calendar_max_score([100., 110., 99.], [1., 1.]))

    def test_halted_zero_return_does_not_replace_a_negative_max(self):
        self.assertAlmostEqual(calendar_max_score([100., 99., 99., 98.], [1., 0., 1.]), .01)
        self.assertIsNone(calendar_max_score([100., 100.], [0.]))
        self.assertIsNone(calendar_max_score([100., None, 98.], [0., 1.]))
        self.assertIsNone(calendar_max_score([100., 99.], [-1.]))
        self.assertIsNone(calendar_max_score([100., math.nan], [1.]))
        self.assertIsNone(calendar_max_score([100., 99.], [math.inf]))
        with self.assertRaises(ValueError):
            calendar_max_score([100., 99., 98.], [1.])

    def test_formation_uses_the_entire_previous_calendar_month_and_historical_members(self):
        class Prices:
            calendar = tuple(date.fromisoformat(d) for d in (
                '2023-11-30', '2023-12-01', '2023-12-04', '2023-12-29',
                '2024-01-02', '2024-01-03', '2024-01-31', '2024-02-01', '2026-01-05'))
            def __init__(self): self.reads = []; self.future_multiplier = 1.
            def value(self, code, field, day):
                self.reads.append(day)
                if day > '2024-01-31': raise AssertionError('future read')
                if field in ('volume', 'factor'): return 1.
                i = int(code[-3:])
                return {'2023-11-30': 100., '2023-12-01': 100. + i,
                        '2023-12-04': 100., '2023-12-29': 100.,
                        '2024-01-02': 100. * self.future_multiplier,
                        '2024-01-03': 100., '2024-01-31': 100.}[day]
        memberships = {f'SH600{i:03d}': [('2020-01-01', '2025-12-31')] for i in range(200)}
        memberships['SZ000999'] = [('2024-01-02', '2025-12-31')]
        source = Prices()
        targets, receipts = build_targets(source, memberships, end='2024-01-31')
        row = receipts[0]
        self.assertEqual(row['formation_asof'], '2023-12-29')
        self.assertEqual(row['return_month'], '2023-12')
        self.assertEqual(row['baseline_close_day'], '2023-11-30')
        self.assertEqual(row['return_begin'], '2023-12-01')
        self.assertEqual(row['daily_return_observations'], 3)
        chosen = targets['low_max_calendar']['2024-01-02']['weights']
        self.assertEqual(tuple(chosen), tuple(f'SH600{i:03d}' for i in range(20)))
        self.assertNotIn('SZ000999', targets['eligible_equal_weight']['2024-01-02']['weights'])
        self.assertAlmostEqual(sum(chosen.values()), .95)
        source.future_multiplier = 1000.
        self.assertEqual(build_targets(source, memberships, end='2024-01-31')[0], targets)
        self.assertLessEqual(max(source.reads), '2023-12-29')
        with self.assertRaises(ValueError): build_targets(source, memberships, end='2026-01-05')

    def test_missing_month_boundary_fails_instead_of_using_partial_month(self):
        class Prices:
            calendar = (date(2023, 12, 1), date(2023, 12, 29), date(2024, 1, 2))
            def value(self, *args): return 100.
        members = {f'SH600{i:03d}': [('2020-01-01', '2025-12-31')] for i in range(200)}
        with self.assertRaises(ValueError): build_targets(Prices(), members, end='2024-01-02')
