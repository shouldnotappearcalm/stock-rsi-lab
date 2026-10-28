import importlib.util
import math
import random
import unittest


@unittest.skipUnless(importlib.util.find_spec('qlib'), 'optional Qlib research dependency unavailable')
class StrictExchangeTests(unittest.TestCase):
    def test_rounding_never_enlarges_request_and_keeps_whole_units(self):
        from stock_rsi.strict_qlib_exchange import strict_floor_units
        rng = random.Random(20170407)
        for _ in range(10000):
            factor = 10 ** rng.uniform(-3, 1); amount = rng.uniform(0, 1000000)
            rounded = strict_floor_units(amount, factor, 100)
            self.assertLessEqual(rounded, amount)
            self.assertGreaterEqual(rounded, 0)
            self.assertAlmostEqual(rounded * factor / 100, round(rounded * factor / 100), places=8)

    def test_precision_allowance_cannot_buy_an_extra_lot(self):
        from stock_rsi.strict_qlib_exchange import strict_floor_units
        self.assertEqual(strict_floor_units(99.95, 1, 100), 0)
        self.assertEqual(strict_floor_units(199.95, 1, 100), 100)
        self.assertEqual(strict_floor_units(100, 1, 100), 100)
        self.assertEqual(strict_floor_units(0, 1, 100), 0)

    def test_bad_factor_and_request_fail_closed(self):
        from stock_rsi.strict_qlib_exchange import strict_floor_units
        for values in [(1, 0, 100), (1, math.nan, 100), (-1, 1, 100), (math.inf, 1, 100), (1, 1, 0)]:
            with self.assertRaises(ValueError): strict_floor_units(*values)
