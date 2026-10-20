import math
from datetime import date
import unittest

from stock_rsi.prior_close_orders import AsOfPrices
try:
    from stock_rsi.budgeted_lot_orders import plan_budgeted_lot_orders
except ImportError:
    plan_budgeted_lot_orders = None


def view(prices, factors=None):
    class Source:
        def value(self, code, field, day):
            assert day == '2023-12-29', 'future or different-session quote used'
            return prices.get(code) if field == 'close' else (factors or {}).get(code, 1.)
    return AsOfPrices(Source(), date(2023, 12, 29))


class BudgetedLotOrderTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(plan_budgeted_lot_orders)

    def test_remaining_budget_reduces_tracking_error_with_legal_lots(self):
        orders, receipt = plan_budgeted_lot_orders(10000., {}, {'A': .475, 'B': .475}, view({'A': 7., 'B': 13.}))
        self.assertEqual([(r['instrument'], r['side'], r['normalized_units']) for r in orders],
                         [('A', 'BUY', 600.), ('B', 'BUY', 400.)])
        self.assertAlmostEqual(receipt['initial_planned_notional'], 8100.)
        self.assertAlmostEqual(receipt['final_planned_notional'], 9400.)
        self.assertAlmostEqual(receipt['target_notional_budget'], 9500.)
        self.assertAlmostEqual(receipt['squared_tracking_error_before'], 1025000.)
        self.assertAlmostEqual(receipt['squared_tracking_error_after'], 505000.)
        self.assertEqual([s['instrument'] for s in receipt['allocation_steps']], ['B'])

    def test_retained_odd_balance_does_not_create_a_pointless_sell_or_double_floor_buy(self):
        orders, receipt = plan_budgeted_lot_orders(10000., {'A': 950.}, {'A': .95}, view({'A': 10.}))
        self.assertEqual(orders, ())
        self.assertEqual(receipt['final_planned_notional'], 9500.)
        orders, receipt = plan_budgeted_lot_orders(10000., {'A': 150.}, {'A': .95}, view({'A': 10.}))
        self.assertEqual([(o['side'], o['normalized_units']) for o in orders], [('BUY', 800.)])
        self.assertEqual(receipt['post_order_normalized_positions'], {'A': 950.})

    def test_budget_can_cancel_a_sell_without_inventing_a_fractional_buy(self):
        orders, receipt = plan_budgeted_lot_orders(10000., {'A': 300., 'B': 600.},
            {'A': .285, 'B': .665}, view({'A': 10., 'B': 10.}))
        self.assertEqual(orders, ())
        self.assertEqual(receipt['final_planned_notional'], 9000.)
        self.assertEqual(receipt['allocation_steps'][0]['action'], 'CANCEL_REMAINING_SELL')

    def test_missing_exit_quote_still_allows_known_inventory_exit_and_sell_first_ordering(self):
        orders, _ = plan_budgeted_lot_orders(20000., {'A': 1000., 'C': 50.},
            {'A': .2375, 'B': .2375}, view({'A': 10., 'B': 10.}))
        self.assertEqual([(o['instrument'], o['side'], o['normalized_units']) for o in orders],
                         [('A', 'SELL', 500.), ('C', 'SELL', 50.), ('B', 'BUY', 400.)])
        self.assertIsNone(orders[1]['known_normalized_close'])

    def test_no_forced_purchase_when_one_lot_worsens_error_or_exceeds_budget(self):
        orders, receipt = plan_budgeted_lot_orders(1000., {}, {'A': .95}, view({'A': 20.}))
        self.assertEqual(orders, ())
        self.assertEqual(receipt['final_planned_notional'], 0.)
        self.assertEqual(receipt['allocation_steps'], [])

    def test_normalization_does_not_change_raw_lots_or_notional(self):
        orders, receipt = plan_budgeted_lot_orders(10000., {}, {'A': .475, 'B': .475},
            view({'A': 5., 'B': 13.}, {'A': .5, 'B': 1.3}))
        self.assertAlmostEqual(orders[0]['normalized_units'] * .5, 500.)
        self.assertAlmostEqual(orders[1]['normalized_units'] * 1.3, 400.)
        self.assertAlmostEqual(receipt['final_planned_notional'], 9000.)

    def test_stable_ties_and_nonpositive_improvements_are_not_pnl_inputs(self):
        orders, receipt = plan_budgeted_lot_orders(10000., {}, {'B': .475, 'A': .475}, view({'A': 10., 'B': 10.}))
        self.assertEqual([s['instrument'] for s in receipt['allocation_steps']], ['A'])
        self.assertEqual([o['normalized_units'] for o in orders], [500., 400.])
        self.assertLessEqual(receipt['final_planned_notional'], receipt['target_notional_budget'])
        self.assertTrue(all(s['squared_error_reduction'] > 0 for s in receipt['allocation_steps']))

    def test_invalid_or_future_inputs_fail_closed(self):
        for bad in (None, 0., -1., math.inf, math.nan):
            with self.assertRaises(ValueError):
                plan_budgeted_lot_orders(10000., {}, {'A': .95}, view({'A': bad}))
        for weights in ({'A': 1.01}, {'A': -1.}, {'A': math.nan}):
            with self.assertRaises(ValueError):
                plan_budgeted_lot_orders(10000., {}, weights, view({'A': 10.}))
        with self.assertRaises(ValueError):
            view({'A': 10.}).value('A', 'close', '2024-01-02')
