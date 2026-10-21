import copy
from decimal import Decimal as D
import unittest

from stock_rsi.monthly_price_risk import CONTRACT, build_overlay_targets, overlay_target
from stock_rsi.raw_share_account import plan_integer_targets


class MonthlyPriceRiskTests(unittest.TestCase):
    def setUp(self):
        self.seed = {'as_of': '2024-04-30', 'weights': {'SH600001': .475, 'SZ000002': .475}}
        self.cells = {code: {'date': self.seed['as_of'], 'close': '1.00', 'tradestatus': '1', 'isST': '0'}
                      for code in self.seed['weights']}

    def test_exact_boundary_keeps_one_yuan_and_excludes_below_it(self):
        self.cells['SZ000002']['close'] = '.99'
        target, receipt = overlay_target(self.seed, self.cells)
        self.assertEqual(set(target['weights']), {'SH600001'})
        self.assertEqual(D(target['weights']['SH600001']), D('.95'))
        self.assertEqual(receipt['blocked'], {'SZ000002': ['FORMATION_RAW_CLOSE_BELOW_CNY1']})
        self.assertFalse(receipt['statutory_delisting_classifier'])

    def test_noop_preserves_exact_original_economic_weights_without_mutation(self):
        before = copy.deepcopy((self.seed, self.cells))
        target, receipt = overlay_target(self.seed, self.cells)
        self.assertEqual(target['weights'], self.seed['weights'])
        self.assertEqual((self.seed, self.cells), before)
        self.assertEqual(receipt['blocked'], {})
        self.assertEqual(target['risk_overlay']['contract'], CONTRACT)

    def test_known_halt_and_ST_are_explicit_reasons_but_unknowns_fail(self):
        self.cells['SH600001'].update(tradestatus='0', close='')
        self.cells['SZ000002']['isST'] = '1'
        target, receipt = overlay_target(self.seed, self.cells)
        self.assertTrue(receipt['all_filtered_to_cash'])
        self.assertEqual(target['weights'], {'SH600001': '0', 'SZ000002': '0'})
        for column in ('tradestatus', 'isST'):
            changed = copy.deepcopy(self.cells)
            changed['SH600001'][column] = ''
            with self.subTest(column=column), self.assertRaises(ValueError):
                overlay_target(self.seed, changed)

    def test_missing_future_extra_or_invalid_active_price_is_rejected(self):
        for change in ('missing_code', 'wrong_day', 'future_field', 'bad_active_price'):
            changed = copy.deepcopy(self.cells)
            if change == 'missing_code':
                del changed['SH600001']
            elif change == 'wrong_day':
                changed['SH600001']['date'] = '2024-05-06'
            elif change == 'future_field':
                changed['SH600001']['future_delisting_day'] = '2024-08-30'
            else:
                changed['SH600001']['close'] = 'NaN'
            with self.subTest(change=change), self.assertRaises(ValueError):
                overlay_target(self.seed, changed)

    def test_remaining_relative_weights_sum_exactly95percent(self):
        seed = {'as_of': '2024-04-30', 'weights': {f'S{i}': .2375 for i in range(4)}}
        cells = {c: {'date': seed['as_of'], 'close': '.99' if c == 'S0' else '10.00',
                     'tradestatus': '1', 'isST': '0'} for c in seed['weights']}
        target, _ = overlay_target(seed, cells)
        self.assertEqual(sum(D(w) for w in target['weights'].values()), D('.95'))
        self.assertEqual(set(target['weights']), {'S1', 'S2', 'S3'})
        self.assertLess(max(D(w) for w in target['weights'].values()) -
                        min(D(w) for w in target['weights'].values()), D('3e-24'))

    def test_all_filtered_cash_representation_sells_owned_odd_lots_without_new_names(self):
        for row in self.cells.values():
            row['close'] = '.99'
        target, _ = overlay_target(self.seed, self.cells)
        orders = plan_integer_targets('10000', {'SH600001': 137}, target['weights'], {'SH600001': D('.99')})
        self.assertEqual(orders, (('SELL', 'SH600001', 137),))
        self.assertEqual(sum(D(w) for w in target['weights'].values()), 0)

    def test_security_names_do_not_determine_eligibility(self):
        self.cells['SZ000002']['close'] = '.99'
        first, receipt = overlay_target(self.seed, self.cells)
        renamed_seed = {**self.seed, 'weights': {'X': .475, 'Y': .475}}
        renamed_cells = {'X': self.cells['SH600001'], 'Y': self.cells['SZ000002']}
        second, other = overlay_target(renamed_seed, renamed_cells)
        self.assertEqual(list(first['weights'].values()), list(second['weights'].values()))
        self.assertEqual(receipt['blocked']['SZ000002'], other['blocked']['Y'])

    def test_provider_only_receives_original_names_at_prior_close_and_future_changes_do_not_matter(self):
        seeds = {'2024-05-06': self.seed}
        calendar = ['2024-04-30', '2024-05-06', '2024-05-07', '2026-01-05']
        source = {(code, '2024-04-30'): copy.deepcopy(row) for code, row in self.cells.items()}
        source[('SH600001', '2026-01-05')] = {'close': '.01', 'future_return': 999}
        calls = []
        def reader(code, day):
            calls.append((code, day))
            return source[(code, day)]
        first = build_overlay_targets(seeds, calendar, reader)
        source[('SH600001', '2026-01-05')] = {'close': '99999', 'future_return': -999}
        second = build_overlay_targets(seeds, calendar, reader)
        self.assertEqual(first, second)
        self.assertEqual(set(calls), {(code, '2024-04-30') for code in self.seed['weights']})
        self.assertEqual(len(calls), 4)

    def test_future_or_nonmonthly_execution_cannot_reach_provider(self):
        def forbidden(*args):
            self.fail('invalid clock reached source provider')
        for day, seed, calendar in [
            ('2026-01-05', {'as_of': '2025-12-31', 'weights': self.seed['weights']}, ['2025-12-31', '2026-01-05']),
            ('2024-05-07', {'as_of': '2024-05-06', 'weights': self.seed['weights']}, ['2024-05-06', '2024-05-07'])]:
            with self.subTest(day=day), self.assertRaises(ValueError):
                build_overlay_targets({day: seed}, calendar, forbidden)


if __name__ == '__main__':
    unittest.main()
