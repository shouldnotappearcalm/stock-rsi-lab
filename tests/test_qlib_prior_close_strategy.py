import importlib.util
import unittest
from datetime import date
from types import SimpleNamespace


@unittest.skipUnless(importlib.util.find_spec("qlib"), "optional Qlib research dependency unavailable")
class PriorCloseStrategyTests(unittest.TestCase):
    def test_native_strategy_never_queries_execution_day_exchange_to_size_orders(self):
        import pandas as pd
        from qlib.backtest.position import Position
        from stock_rsi.qlib_prior_close import MonthlyPriorCloseStrategy

        class Snapshot:
            calendar = (date(2023, 12, 29), date(2024, 1, 2), date(2024, 1, 3))
            calls = []
            future_open = 20.
            def value(self, symbol, field, day):
                self.calls.append((symbol, field, day))
                if day != "2023-12-29":
                    raise AssertionError("future quote leaked into the decision")
                return 10. if field == "close" else 1.
        class ForbiddenExchange:
            def __getattr__(self, name):
                raise AssertionError("execution exchange must not participate in order generation")
        snapshot = Snapshot()
        targets = {"2024-01-02": {"as_of":"2023-12-29", "weights":{"B":.95}}}
        strategy = MonthlyPriorCloseStrategy(targets=targets, snapshot=snapshot)
        position = Position(cash=100000.)
        calendar = SimpleNamespace(get_trade_step=lambda:0,
                                   get_step_time=lambda number=None:(pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-02 23:59:59")))
        strategy.common_infra = SimpleNamespace(get=lambda key:SimpleNamespace(current_position=position))
        strategy.level_infra = SimpleNamespace(get=lambda key:calendar)
        strategy._trade_exchange = ForbiddenExchange()
        orders = strategy.generate_trade_decision().get_decision()
        self.assertEqual([(row.stock_id, row.amount) for row in orders], [("B",9500.)])
        snapshot.future_open = 1000.
        self.assertEqual(strategy.generate_trade_decision().get_decision()[0].amount, 9500.)
        self.assertTrue(all(day == "2023-12-29" for _, _, day in snapshot.calls))
        targets["2024-01-02"]["as_of"] = "2024-01-02"
        with self.assertRaisesRegex(ValueError, "prior session"):
            strategy.generate_trade_decision()
