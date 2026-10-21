import copy
import unittest
from datetime import date

from stock_rsi.ordinary_source_scope import ordinary_source_rows_on
from stock_rsi.calendar import TradingCalendar
from scripts.replay_ordinary_stock_distribution_targets import simulate_fixed_targets
from scripts.replay_stock_distribution_targets import simulate_fixed_targets as original_replay


class OrdinarySourceScopeTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2024, 6, 3)
        self.bars = {
            'SZ000001': {'2024-06-03': {'date': '2024-06-03', 'isST': '0', 'close': '10'}},
            'SZ002092': {'2024-06-03': {'date': '2024-06-03', 'isST': '1', 'close': '5'}},
        }

    def test_unused_nonordinary_row_preserved_as_explicit_unrequired_interval(self):
        before = copy.deepcopy(self.bars)
        rows, audit = ordinary_source_rows_on(self.bars, self.day, {'SZ000001'}, {})
        self.assertEqual(set(rows), {'SZ000001'})
        self.assertEqual(audit, [{
            'instrument': 'SZ002092', 'session': '2024-06-03',
            'reason': 'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT',
            'original_row_present': True, 'source_isST': '1',
            'required_by_account': False, 'synthetic_price_created': False,
        }])
        self.assertEqual(self.bars, before)

    def test_owned_pending_order_or_decision_dependency_on_ST_fails_before_use(self):
        for label in ('owned', 'pending_order', 'pending_stock', 'decision_price'):
            with self.subTest(dependency=label), self.assertRaisesRegex(ValueError, 'required nonordinary'):
                ordinary_source_rows_on(self.bars, self.day, {'SZ000001', 'SZ002092'}, {})

    def test_missing_or_unknown_state_is_not_an_unused_ST_exception(self):
        for value in ('2', '', None, True):
            bars = copy.deepcopy(self.bars)
            bars['SZ002092']['2024-06-03']['isST'] = value
            with self.subTest(state=value), self.assertRaises(ValueError):
                ordinary_source_rows_on(bars, self.day, {'SZ000001'}, {})
        bars = copy.deepcopy(self.bars)
        del bars['SZ002092']['2024-06-03']
        with self.assertRaisesRegex(ValueError, 'unexplained raw source gap'):
            ordinary_source_rows_on(bars, self.day, {'SZ000001'}, {})

    def test_real_account_guard_checks_pending_order_and_existing_owned_shares(self):
        days = ['2023-12-29', '2024-01-02', '2024-01-03']
        code = 'SZ002092'
        for st_day in days[1:]:
            bars = {code: {d: {
                'date': d, 'isST': '1' if d == st_day else '0', 'tradestatus': '1',
                'open': '10', 'close': '10', 'preclose': '10', 'high': '10',
                'low': '10', 'volume': '1000000',
            } for d in days}}
            targets = {days[1]: {'as_of': days[0], 'weights': {code: '.95'}}}
            with self.subTest(first_ST_day=st_day), self.assertRaisesRegex(ValueError, 'required nonordinary'):
                simulate_fixed_targets(TradingCalendar(days), bars, (), targets,
                                                '1000000', lifecycles={})

    def test_all_ordinary_account_preserves_original_integer_orders_and_ledger(self):
        days = ['2023-12-29', '2024-01-02', '2024-01-03']
        bars = {code: {d: {
            'date': d, 'isST': '0', 'tradestatus': '1', 'open': price,
            'close': price, 'preclose': price, 'high': price, 'low': price,
            'volume': '1000000',
        } for d in days} for code, price in [('SZ000001', '13'), ('SZ000002', '17')]}
        targets = {days[1]: {'as_of': days[0], 'weights': {'SZ000001': '.475', 'SZ000002': '.475'}}}
        args = (TradingCalendar(days), bars, (), targets, '1000000')
        self.assertEqual(simulate_fixed_targets(*args, lifecycles={}), original_replay(*args, lifecycles={}))


if __name__ == '__main__':
    unittest.main()
