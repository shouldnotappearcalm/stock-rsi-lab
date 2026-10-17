import unittest
from datetime import date
from types import SimpleNamespace

from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence


class DailyEvidenceTests(unittest.TestCase):
    def fixture(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("optional pandas research dependency unavailable")
        first, second = pd.to_datetime(["2024-01-02", "2024-01-03"])
        report = pd.DataFrame({"account": [999., 1008.], "value": [100., 0.],
                               "total_cost": [1., 2.], "total_turnover": [100., 210.]},
                              index=[first, second])
        def position(cash, shares, price):
            return SimpleNamespace(get_cash=lambda include_settle: cash,
                                   get_stock_list=lambda: ["A"] if shares else [],
                                   get_stock_amount=lambda code: shares,
                                   get_stock_price=lambda code: price)
        positions = {first: position(899., 10., 10.), second: position(1008., 0., 11.)}
        def orders(direction, price, value):
            fields = {"amount": 10., "deal_amount": 10., "trade_price": price,
                      "trade_value": value, "trade_cost": 1., "trade_dir": direction}
            return SimpleNamespace(to_series=lambda: {key: pd.Series({"A": val}) for key, val in fields.items()},
                                   get_index_data=lambda key: pd.Series({"A": fields[key]}))
        history = {first: orders(1, 10., 100.), second: orders(0, 11., -110.)}
        calendar = (date(2023, 12, 29), first.date(), second.date())
        return report, positions, history, calendar

    def test_cash_cost_turnover_and_prior_session_signal_reconcile(self):
        evidence = reconcile_daily_evidence(*self.fixture(), initial_cash=1000.,
                                            signal_days={date(2023, 12, 29), date(2024, 1, 2)})
        self.assertEqual(evidence["days"][0]["signal_date"], "2023-12-29")
        self.assertEqual(evidence["orders"][1]["side"], "SELL")
        self.assertEqual(evidence["holdings"][0]["normalized_units"], 10.)
        self.assertEqual(evidence["total_cost"], 2.)
        self.assertEqual(evidence["total_turnover"], 210.)

    def test_accounting_mismatch_and_missing_prior_signal_fail(self):
        report, positions, history, calendar = self.fixture()
        report.iloc[1, report.columns.get_loc("account")] += 1
        with self.assertRaisesRegex(ValueError, "account"):
            reconcile_daily_evidence(report, positions, history, calendar, initial_cash=1000.,
                                     signal_days=set(calendar))
        report, positions, history, calendar = self.fixture()
        with self.assertRaisesRegex(ValueError, "prior-session signal"):
            reconcile_daily_evidence(report, positions, history, calendar, initial_cash=1000.,
                                     signal_days={date(2024, 1, 2)})

    def test_native_qlib_order_indicator_supports_current_pandas(self):
        try:
            from qlib.backtest.high_performance_ds import NumpyOrderIndicator
        except ImportError:
            self.skipTest("optional Qlib research dependency unavailable")
        report, positions, history, calendar = self.fixture()
        native = {}
        for day, original in history.items():
            indicator = NumpyOrderIndicator()
            for field, values in original.to_series().items():
                indicator.assign(field, values.to_dict())
            native[day] = indicator
        evidence = reconcile_daily_evidence(report, positions, native, calendar, initial_cash=1000.,
                                            signal_days=set(calendar))
        self.assertEqual(evidence["total_cost"], 2.)
