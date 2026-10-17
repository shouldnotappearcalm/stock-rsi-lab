import unittest
from scripts.capture_sina_daily_crosscheck import validate_sina_daily


class SinaDailyCrosscheckTests(unittest.TestCase):
    def row(self, day="2024-01-02"):
        return {"day":day,"open":"2.690","high":"2.740","low":"2.670","close":"2.720","volume":"66861235"}

    def test_traded_daily_values_and_bounded_window_preserve_exact_source_units(self):
        rows,excluded=validate_sina_daily([self.row("2020-01-02"),self.row(),self.row("2027-01-02")])
        self.assertEqual(rows,[self.row()])
        self.assertEqual(excluded,{"before_window":1,"after_window":1})

    def test_null_missing_bad_prices_and_fractional_volume_are_never_valid_zero(self):
        for payload in (None,[],{},[self.row()|{"volume":True}],[self.row()|{"close":"NaN"}],
                        [self.row()|{"volume":"1.5"}],[self.row()|{"high":"2.6"}],
                        [self.row()|{"open":None}],[self.row()|{"volume":"0","high":"2.6"}]):
            with self.subTest(payload=payload),self.assertRaises(ValueError):validate_sina_daily(payload)

    def test_duplicates_intraday_frequency_and_out_of_order_dates_fail(self):
        for payload in ([self.row(),self.row()],[self.row("2024-01-02 09:35:00")],
                        [self.row("2024-01-03"),self.row()]):
            with self.subTest(payload=payload),self.assertRaises(ValueError):validate_sina_daily(payload)
