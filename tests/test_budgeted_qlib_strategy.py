import importlib.util
import unittest
from datetime import date
from types import SimpleNamespace


@unittest.skipUnless(importlib.util.find_spec('qlib'), 'optional Qlib research dependency unavailable')
class BudgetedQlibStrategyTests(unittest.TestCase):
    def test_order_sizes_and_receipt_use_only_prior_close_account_and_quotes(self):
        import pandas as pd
        from qlib.backtest.position import Position
        try:
            from stock_rsi.budgeted_qlib_strategy import BudgetedMonthlyPriorCloseStrategy
        except ImportError:
            BudgetedMonthlyPriorCloseStrategy = None
        self.assertIsNotNone(BudgetedMonthlyPriorCloseStrategy)

        class Snapshot:
            calendar = (date(2023, 12, 29), date(2024, 1, 2), date(2024, 1, 3))
            def value(self, code, field, day):
                if day != '2023-12-29':
                    raise AssertionError('future quote used')
                return {'A': 7., 'B': 13.}[code] if field == 'close' else 1.
        class ForbiddenExchange:
            def __getattr__(self, name):
                raise AssertionError('execution exchange used to generate order')
        targets = {'2024-01-02': {'as_of': '2023-12-29', 'weights': {'A': .475, 'B': .475}}}
        strategy = BudgetedMonthlyPriorCloseStrategy(targets=targets, snapshot=Snapshot())
        position = Position(cash=10000.)
        day = ['2024-01-02']
        calendar = SimpleNamespace(get_trade_step=lambda: 0, get_step_time=lambda number=None:
            (pd.Timestamp(day[0]), pd.Timestamp(day[0]+' 23:59:59')))
        strategy.common_infra = SimpleNamespace(get=lambda key: SimpleNamespace(current_position=position))
        strategy.level_infra = SimpleNamespace(get=lambda key: calendar)
        strategy._trade_exchange = ForbiddenExchange()
        result = strategy.generate_trade_decision().get_decision()
        self.assertEqual([(o.stock_id, o.amount) for o in result], [('A', 600.), ('B', 400.)])
        receipt = strategy.intents[0]['allocation_receipt']
        self.assertEqual(receipt['final_planned_notional'], 9400.)
        self.assertEqual(strategy.intents[0]['latest_decision_price_read'], '2023-12-29')
        day[0] = '2024-01-03'
        self.assertEqual(strategy.generate_trade_decision().get_decision(), [])
        self.assertEqual(len(strategy.intents), 1)
        day[0] = '2024-01-02'
        targets['2024-01-02']['as_of'] = '2024-01-02'
        with self.assertRaisesRegex(ValueError, 'prior session'):
            strategy.generate_trade_decision()
