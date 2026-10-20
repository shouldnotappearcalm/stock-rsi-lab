from datetime import date
from decimal import Decimal
import unittest

try:
    from stock_rsi.budgeted_raw_orders import plan_budgeted_raw_targets, RawPriorCloseView
except ImportError:
    plan_budgeted_raw_targets = RawPriorCloseView = None


class BudgetedRawOrdersTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(plan_budgeted_raw_targets)
        self.day = date(2025, 5, 30)

    def test_preserves_existing_odd_shares_when_adding_a_whole_lot(self):
        orders,receipt=plan_budgeted_raw_targets('20000',{'SH600001':130},{'SH600001':'.95'}, {'SH600001':'30'},self.day)
        self.assertEqual(orders,(('BUY','SH600001',500),))
        self.assertEqual(receipt['post_order_normalized_positions']['SH600001'],630)
        self.assertLessEqual(receipt['final_planned_notional'],19000)

    def test_remaining_budget_adds_only_tracking_improving_affordable_lot(self):
        orders,receipt=plan_budgeted_raw_targets('10000',{}, {'SH600001':'.45','SH600002':'.5'}, {'SH600001':'16','SH600002':'11'},self.day)
        self.assertEqual(orders,(('BUY','SH600001',300),('BUY','SH600002',400)))
        self.assertLessEqual(receipt['final_planned_notional'],9500)
        self.assertEqual(len(receipt['allocation_steps']),1)
        self.assertLess(receipt['squared_tracking_error_after'],receipt['squared_tracking_error_before'])
        self.assertFalse(receipt['execution_prices_or_returns_used'])

    def test_zero_target_exits_all_odd_inventory_without_requiring_price(self):
        orders,_=plan_budgeted_raw_targets('10000',{'SH600002':137},{'SH600001':'.95'}, {'SH600001':'10'},self.day)
        self.assertIn(('SELL','SH600002',137),orders)
        self.assertEqual(orders[0],('SELL','SH600002',137))

    def test_rejects_invalid_inventory_prices_weights_and_unrepresentable_float(self):
        for equity,positions,weights,prices in (
            ('10000',{'SH600001':100.5},{'SH600001':'.95'},{'SH600001':'10'}),
            ('10000',{}, {'SH600001':'NaN'},{'SH600001':'10'}),
            ('10000',{}, {'SH600001':'1.01'},{'SH600001':'10'}),
            ('10000',{}, {'SH600001':'.95'},{'SH600001':'10.001'}),
            ('10000',{}, {'SH600001':'.95'},{'SH600001':'0'}),
            ('10000',{}, {'SH600001':'.95'},{}),
            ('10000',{'SH600001':2**53+1},{'SH600001':'.95'},{'SH600001':'10'}),
            ('100000000000000000000',{}, {'SH600001':'.95'},{'SH600001':'.01'}),
        ):
            with self.subTest(positions=positions,weights=weights,prices=prices):
                with self.assertRaises(ValueError):plan_budgeted_raw_targets(equity,positions,weights,prices,self.day)

    def test_rejects_when_float_planner_receipt_claims_a_lot_not_emitted(self):
        # Existing allocator uses a relative delta tolerance at enormous balances.
        # The raw bridge must refuse a receipt that differs from emitted orders.
        with self.assertRaisesRegex(ValueError,'receipt differs from emitted physical orders'):
            plan_budgeted_raw_targets('20000000200',{'SH600001':10000000000},
                {'SH600001':'.5'},{'SH600001':'1.00'},self.day)

    def test_orders_are_invariant_to_normalized_share_coordinates(self):
        from random import Random
        from types import SimpleNamespace
        from stock_rsi.budgeted_lot_orders import plan_budgeted_lot_orders
        rng=Random(21021)
        for _ in range(100):
            positions={'SH600001':rng.randrange(0,3000),'SH600002':rng.randrange(0,3000)}
            prices={'SH600001':str(rng.randrange(200,10000)/100),'SH600002':str(rng.randrange(200,10000)/100)}
            weights={'SH600001':'.45','SH600002':'.5'}
            raw,_=plan_budgeted_raw_targets('200000',positions,weights,prices,self.day)
            for factor in (.5,2.,4.):
                def value(code,field,day):
                    self.assertEqual(day,self.day.isoformat())
                    return float(prices[code])*factor if field=='close' else factor
                view=SimpleNamespace(as_of=self.day,value=value)
                normalized,_=plan_budgeted_lot_orders(200000.,{c:q/factor for c,q in positions.items()},
                    {c:float(w) for c,w in weights.items()},view)
                converted=tuple((r['side'],r['instrument'],int(r['normalized_units']*factor)) for r in normalized)
                self.assertEqual(raw,converted)

    def test_view_can_only_read_prior_close_and_unity_coordinate_factor(self):
        view=RawPriorCloseView(self.day,{'SH600001':'12.34'})
        self.assertEqual(view.value('SH600001','close',self.day.isoformat()),12.34)
        self.assertEqual(view.value('SH600001','factor',self.day.isoformat()),1.)
        for field,day in (('open',self.day.isoformat()),('close','2025-06-02')):
            with self.assertRaises(ValueError):view.value('SH600001',field,day)


if __name__=='__main__':unittest.main()
