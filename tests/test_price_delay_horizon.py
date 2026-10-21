from datetime import date, timedelta
import random
import unittest

from stock_rsi import price_delay
from stock_rsi import price_delay_horizon as horizon


class SyntheticPrices:
    """Synthetic regression calendar; never a real exchange-session source."""
    def __init__(self, future_tail):
        self.calendar = []
        day = date(2022, 1, 1)
        while day <= date(2026, 1, 30):
            if day.weekday() < 5 and day not in (date(2024, 1, 1), date(2026, 1, 1), date(2026, 1, 2)):
                self.calendar.append(day)
            day += timedelta(days=1)
        self.indices = {d: i for i, d in enumerate(self.calendar)}
        self.calls = []
        self.tail = future_tail
        rng = random.Random(985)
        self.prices = [100.]
        for _ in self.calendar:
            self.prices.append(self.prices[-1] * (1 + rng.uniform(-.015, .015)))

    def value(self, code, field, day):
        day = date.fromisoformat(day)
        self.calls.append(day)
        if day > date(2025, 12, 31):
            return self.tail
        if field == 'factor':
            return 1.
        if field == 'volume':
            return 10000.
        return self.prices[max(0, self.indices[day] - (0 if code == 'SH000905' else 5))]


class PriceDelayHorizonTests(unittest.TestCase):
    names = {f'SZ{i:06d}': [('2020-01-01', '2026-10-20')] for i in range(1, 201)}

    def test_extension_preserves_old_policy_and_future_values_cannot_change_January_decision(self):
        old = price_delay.build_targets(SyntheticPrices(999999.), self.names,
                                        start='2024-01-02', end='2024-01-02')
        same = horizon.build_targets(SyntheticPrices(-999999.), self.names,
                                     start='2024-01-02', end='2024-01-02')
        self.assertEqual(old, same)
        a, b = SyntheticPrices(999999.), SyntheticPrices(-999999.)
        first = horizon.build_targets(a, self.names, start='2026-01-05', end='2026-01-05')
        second = horizon.build_targets(b, self.names, start='2026-01-05', end='2026-01-05')
        self.assertEqual(first, second)
        self.assertEqual(first[1][0]['measurement_cap'], '2025-11-30')
        self.assertEqual(first[1][0]['latest_formation_price_read'], '2025-12-31')
        self.assertLessEqual(max(a.calls), date(2025, 12, 31))

    def test_outside_registered_interim_cutoff_fails_before_prices(self):
        with self.assertRaises(ValueError):
            horizon.build_targets(None, {}, end='2026-10-21')
        with self.assertRaises(ValueError):
            price_delay.build_targets(None, {}, start='2026-01-05', end='2026-01-05')


if __name__ == '__main__':
    unittest.main()
