import copy
from decimal import Decimal
import unittest

from stock_rsi import annual_profitability as factor


def pages(year=2023, unit='元', cost='70.00'):
    return [f'''合并资产负债表
{year} 年12月31日
单位:{unit} 币种:人民币
项目 附注 {year}年12月31日 {year-1}年12月31日
资产总计 七、1 200.00 100.00
''', '''母公司资产负债表
资产总计 999.00 888.00
''', f'''合并利润表
{year}年1—12月
单位:{unit} 币种:人民币
项目 附注 {year}年度 {year-1}年度
一、营业总收入 120.00 100.00
其中：营业收入 七、61 100.00 80.00
二、营业总成本 90.00 85.00
其中：营业成本 {cost} 60.00
''', '''母公司利润表
营业收入 999.00 888.00
营业成本 1.00 2.00
''']


def record(year=2023, publication='2024-04-27', cost='70.00', fiscal=None, doc='a'):
    cells = factor.parse_consolidated_tables(pages(year, cost=cost), year)
    fiscal = fiscal or f'{year}-12-31'
    return factor.make_observation('SH600001', year, fiscal, publication, '2026-10-17T12:00:00+00:00',
                                   doc * 64, '123456', cells[fiscal])


class AnnualProfitabilityTests(unittest.TestCase):
    def test_exact_consolidated_rows_and_columns_ignore_total_cost_and_parent_table(self):
        data = factor.parse_consolidated_tables(pages(), 2023)
        self.assertEqual(data['2023-12-31']['revenue']['value_CNY'], '100.00')
        self.assertEqual(data['2023-12-31']['cost_of_sales']['value_CNY'], '70.00')
        self.assertEqual(data['2023-12-31']['total_assets']['value_CNY'], '200.00')
        self.assertEqual(data['2022-12-31']['revenue']['value_CNY'], '80.00')
        self.assertEqual(data['2022-12-31']['cost_of_sales']['column_index'], 1)
        self.assertEqual(data['2023-12-31']['revenue']['page'], 3)
        self.assertEqual(data['2023-12-31']['total_assets']['header_page'], 1)

    def test_explicit_currency_unit_normalization_and_ratio(self):
        data = factor.parse_consolidated_tables(pages(unit='万元'), 2023)
        self.assertEqual(data['2023-12-31']['revenue']['value_CNY'], '1000000.00')
        r = factor.make_observation('SH600001', 2023, '2023-12-31', '2024-04-27',
              '2026-10-17T12:00:00+00:00', 'a'*64, '123456', data['2023-12-31'])
        s = factor.snapshot_observations([r], '2024-04-29T15:05:00+08:00', mode=factor.RECONSTRUCTED)
        self.assertEqual(Decimal(s['records'][0]['gross_profit_to_assets']), Decimal('.15'))

    def test_missing_units_wrong_currency_duplicate_table_and_unknown_columns_fail(self):
        changes = [lambda p: [x.replace('单位:元', '单位:百万元') for x in p],
                   lambda p: [x.replace('人民币', '美元') for x in p],
                   lambda p: [*p, p[2]],
                   lambda p: [x.replace('2023年度 2022年度', '2022年度 2023年度') for x in p],
                   lambda p: [x.replace('200.00 100.00', '200.00 100.00 90.00') for x in p]]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                factor.parse_consolidated_tables(change(pages()), 2023)

    def test_missing_duplicate_empty_nonfinite_zero_assets_and_bad_grouping_fail(self):
        for before, after in [('资产总计 七、1 200.00 100.00', '资产总计 0.00 100.00'),
                              ('200.00 100.00', 'NaN 100.00'), ('70.00 60.00', ' 60.00'),
                              ('70.00 60.00', '1,00.00 60.00'),
                              ('其中：营业成本 70.00 60.00', '其中：营业成本 70.00 60.00\n营业成本 1.00 2.00')]:
            p = [x.replace(before, after) for x in pages()]
            with self.subTest(after=after), self.assertRaises(ValueError):
                factor.parse_consolidated_tables(p, 2023)

    def test_negative_gross_profit_is_preserved_without_clipping(self):
        r = record(cost='110.00')
        s = factor.snapshot_observations([r], '2025-01-01T00:00:00+00:00', mode=factor.RECONSTRUCTED)
        self.assertEqual(s['records'][0]['gross_profit_CNY'], '-10.00')
        self.assertEqual(Decimal(s['records'][0]['gross_profit_to_assets']), Decimal('-.05'))

    def test_observed_mode_does_not_backdate_2026_capture_into_2024(self):
        r = record()
        s = factor.snapshot_observations([r], '2024-12-31T15:05:00+08:00')
        self.assertEqual(s['records'], [])
        self.assertFalse(s['conditional_publication_day_reconstruction'])
        self.assertEqual(len(factor.snapshot_observations([r], '2026-10-17T12:00:00+00:00')['records']), 1)

    def test_publication_day_end_is_explicit_and_not_midnight_arrival(self):
        r = record()
        for timestamp in ['2024-04-26T15:05:00+08:00', '2024-04-27T00:00:00+08:00',
                          '2024-04-27T23:59:59+08:00']:
            self.assertEqual(factor.snapshot_observations([r], timestamp, mode=factor.RECONSTRUCTED)['records'], [])
        s = factor.snapshot_observations([r], '2024-04-28T00:00:00+08:00', mode=factor.RECONSTRUCTED)
        self.assertEqual(len(s['records']), 1)
        self.assertTrue(s['conditional_publication_day_reconstruction'])
        self.assertFalse(s['investment_factor_admitted'])

    def test_later_comparative_restatement_cannot_replace_earlier_snapshot(self):
        old = record()
        newcells = factor.parse_consolidated_tables(pages(2024), 2024)['2023-12-31']
        revised = factor.make_observation('SH600001', 2024, '2023-12-31', '2025-04-26',
                   '2026-10-17T12:00:00+00:00', 'b'*64, '654321', newcells)
        before = factor.snapshot_observations([old], '2024-12-31T15:05:00+08:00', mode=factor.RECONSTRUCTED)
        self.assertEqual(factor.snapshot_observations([revised, old], before['as_of'], mode=factor.RECONSTRUCTED), before)
        after = factor.snapshot_observations([revised, old], '2025-05-01T00:00:00+08:00', mode=factor.RECONSTRUCTED)
        self.assertEqual(after['records'][0]['record_id'], revised['record_id'])
        self.assertEqual(after['records'][0]['gross_profit_CNY'], '20.00')

    def test_future_payload_is_not_hashed_validated_or_decoded_before_visibility(self):
        old = record()
        future = record(year=2024, publication='2025-04-26', doc='b')
        future['payload'] = {'corrupted_future_numeric_field': 'must never decode'}
        before = factor.snapshot_observations([old], '2024-12-31T00:00:00+00:00', mode=factor.RECONSTRUCTED)
        self.assertEqual(factor.snapshot_observations([old, future], before['as_of'], mode=factor.RECONSTRUCTED), before)
        with self.assertRaisesRegex(ValueError, 'record changed'):
            factor.snapshot_observations([old, future], '2025-05-01T00:00:00+00:00', mode=factor.RECONSTRUCTED)

    def test_duplicate_identical_observation_is_idempotent_but_same_day_ambiguity_fails(self):
        r = record()
        one = factor.snapshot_observations([r], '2025-01-01T00:00:00+00:00', mode=factor.RECONSTRUCTED)
        self.assertEqual(factor.snapshot_observations([r, copy.deepcopy(r)], one['as_of'], mode=factor.RECONSTRUCTED), one)
        with self.assertRaisesRegex(ValueError, 'ambiguous same-day'):
            factor.snapshot_observations([r, record(doc='b')], one['as_of'], mode=factor.RECONSTRUCTED)

    def test_bad_scope_unit_evidence_chronology_and_naive_clock_fail(self):
        data = factor.parse_consolidated_tables(pages(), 2023)['2023-12-31']
        for field, key, value in [('total_assets', 'statement', '母公司资产负债表'),
                                  ('revenue', 'value_CNY', '1000.00'), ('revenue', 'fiscal_end', '2022-12-31')]:
            changed = copy.deepcopy(data)
            changed[field][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                factor.make_observation('SH600001', 2023, '2023-12-31', '2024-04-27',
                    '2026-10-17T12:00:00+00:00', 'a'*64, '123456', changed)
        with self.assertRaises(ValueError):
            record(publication='2023-01-01')
        with self.assertRaisesRegex(ValueError, 'timezone-aware'):
            factor.snapshot_observations([record()], '2024-12-31T15:05:00')
        with self.assertRaises(ValueError):
            factor.snapshot_observations([record()], '2024-12-31T15:05:00+08:00', mode='AS_IF_PIT')


if __name__ == '__main__':
    unittest.main()
