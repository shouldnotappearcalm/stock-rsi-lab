import unittest
from datetime import date
from stock_rsi.blogger_batch6 import evaluate


class CalendarStrategyTests(unittest.TestCase):
    def test_turn_of_month_counts_actual_sessions_across_holidays(self):
        dates = tuple(map(date.fromisoformat, (
            '2025-12-30', '2025-12-31', '2026-01-05', '2026-01-06',
            '2026-01-07', '2026-01-08', '2026-01-09',
        )))
        targets = [bool(evaluate('monthturn4', dates, d)['leader']) for d in dates[1:-1]]
        self.assertEqual(targets, [True, True, True, True, False])

    def test_halloween_switches_at_actual_open(self):
        dates = tuple(map(date.fromisoformat, (
            '2024-04-29', '2024-04-30', '2024-05-06', '2024-10-31',
            '2024-11-01', '2024-11-04',
        )))
        targets = [bool(evaluate('halloween6', dates, d)['leader']) for d in dates[1:-1]]
        self.assertEqual(targets, [True, False, False, True])

    def test_requires_scheduled_day_and_next_calendar_date(self):
        dates = tuple(map(date.fromisoformat, ('2025-12-30','2025-12-31','2026-01-05')))
        for day in (date(2026,1,1), dates[-1]):
            with self.assertRaises(ValueError):
                evaluate('monthturn4', dates, day)
