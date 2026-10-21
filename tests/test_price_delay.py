from datetime import date, timedelta
import importlib
import importlib.util
import random
import unittest


def module(test):
    if importlib.util.find_spec('stock_rsi.price_delay') is None:
        test.fail('the separately registered price-delay factor is not implemented')
    return importlib.import_module('stock_rsi.price_delay')


class PriceDelayTests(unittest.TestCase):
    def samples(self):
        rng = random.Random(2005)
        return [[rng.gauss(0, .02) for _ in range(5)] for _ in range(52)]

    def test_contemporaneous_response_has_no_delay_and_recovers_coefficients(self):
        m = module(self); x = self.samples(); r = m.fit_delay([.01+2*v[0] for v in x], x)
        self.assertAlmostEqual(r['delay'], 0, places=10)
        self.assertAlmostEqual(r['coefficients'][0], 2, places=10)
        self.assertAlmostEqual(r['alpha'], .01, places=10)

    def test_lagged_response_has_high_delay_on_same_paired_sample(self):
        m = module(self); x = self.samples(); r = m.fit_delay([1.5*v[1] for v in x], x)
        self.assertGreater(r['delay'], .8)
        self.assertAlmostEqual(r['r2_full'], 1, places=10)
        self.assertAlmostEqual(r['coefficients'][1], 1.5, places=10)
        self.assertEqual(r['observations'], 52)

    def test_degenerate_and_undercovered_regressions_are_not_ranked(self):
        m = module(self); x = self.samples()
        self.assertIsNone(m.fit_delay([1.0]*52, x))
        self.assertIsNone(m.fit_delay([v[0] for v in x[:39]], x[:39]))
        self.assertIsNone(m.fit_delay([v[0] for v in x], [[v[0]]*5 for v in x]))

    def test_holiday_marker_uses_last_observed_session_and_never_next_session(self):
        m = module(self); days = []
        d = date(2022, 1, 1)
        while d <= date(2023, 12, 1):
            if d.weekday() < 5 and d != date(2023, 11, 29): days.append(d)
            d += timedelta(days=1)
        ends = m.weekly_endpoints(days, date(2023, 11, 30))
        self.assertEqual(ends[-1], {'marker': date(2023, 11, 29), 'session': date(2023, 11, 28)})
        self.assertTrue(all(r['session'] <= r['marker'] <= date(2023, 11, 30) for r in ends))

    def test_future_prices_cannot_change_old_scores_targets_or_receipts(self):
        m = module(self)
        class Snapshot:
            def __init__(self, tail):
                self.tail = tail; self.calendar = []; self.calls = []
                d = date(2022, 1, 1)
                while d <= date(2024, 1, 31):
                    if d.weekday() < 5 and d != date(2024, 1, 1): self.calendar.append(d)
                    d += timedelta(days=1)
                rng = random.Random(985); self.prices = [100.]
                for _ in self.calendar: self.prices.append(self.prices[-1]*(1+rng.uniform(-.015, .015)))
                self.indices = {d: i for i, d in enumerate(self.calendar)}
            def value(self, code, field, day):
                d = date.fromisoformat(day); self.calls.append(d)
                if d > date(2023, 12, 29): return self.tail
                if field == 'factor': return 1.
                if field == 'volume': return 10000.
                i = self.indices[d]
                return self.prices[max(0, i-(0 if code == 'SH000905' else 5))]
        names = {f'SZ{i:06d}': [('2020-01-01', '2025-12-31')] for i in range(1, 201)}
        a, b = Snapshot(999999.), Snapshot(-999999.)
        first = m.build_targets(a, names, start='2024-01-02', end='2024-01-02')
        second = m.build_targets(b, names, start='2024-01-02', end='2024-01-02')
        self.assertEqual(first, second)
        receipt = first[1][0]
        self.assertEqual(receipt['measurement_cap'], '2023-11-30')
        self.assertLessEqual(receipt['latest_measurement_price_read'], '2023-11-30')
        self.assertEqual(receipt['latest_formation_price_read'], '2023-12-29')
        self.assertLessEqual(max(a.calls), date(2023, 12, 29))

    def test_2026_request_fails_before_any_snapshot_read(self):
        m = module(self)
        with self.assertRaises(ValueError):
            m.build_targets(None, {}, start='2026-01-01', end='2026-01-31')


if __name__ == '__main__': unittest.main()
