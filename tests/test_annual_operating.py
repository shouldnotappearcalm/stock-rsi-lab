import copy
from decimal import Decimal
import unittest

try:
    from stock_rsi import annual_operating as op
except ImportError:
    op = None

from tests.test_annual_profitability import pages


def source(year=2023, unit='元', cost='60.00', admin='5.00', research='7.00'):
    result = pages(year, unit=unit, cost=cost)
    result[2] += (f'销售费用 七、63 10.00 8.00\n管理费用 七、64 {admin} 2.00\n'
                  f'研发费用 七、65 {research} 6.00\n')
    return result


class AnnualOperatingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(op, 'annual operating source module missing')

    def report(self, year=2023, publication='2024-04-27', doc='a', **kwargs):
        return op.make_report('SH600001', year, publication, '2026-10-23T00:00:00+00:00',
                              doc * 64, '123456', op.parse_report(source(year, **kwargs), year))

    def snapshot(self, reports, as_of='2024-12-31T15:05:00+08:00', **kwargs):
        return op.snapshot_reports(reports, as_of, mode=op.RECONSTRUCTED, **kwargs)

    def test_current_ratio_uses_same_edition_prior_assets_and_never_computes_comparative_ratio(self):
        record = self.report()
        result = self.snapshot([record])
        self.assertEqual(len(result['records']), 1)
        row = result['records'][0]
        self.assertEqual(row['fiscal_end'], '2023-12-31')
        self.assertEqual(row['operating_profit_CNY'], '25.00')
        self.assertEqual(row['lagged_assets_CNY'], '100.00')
        self.assertEqual(Decimal(row['operating_profit_to_lagged_assets']), Decimal('.25'))
        self.assertEqual(record['payload']['parsed']['income']['2022-12-31']['selling_expenses']['value_CNY'], '8.00')
        self.assertFalse(result['investment_factor_admitted'])
        self.assertTrue(result['all_visible_supported_editions_not_latest_eligibility'])

    def test_separately_reported_research_does_not_get_added_or_subtracted_again(self):
        a = self.snapshot([self.report(research='7.00')])['records'][0]
        b = self.snapshot([self.report(research='700.00')])['records'][0]
        self.assertEqual(a['operating_profit_CNY'], '25.00')
        self.assertEqual(a['operating_profit_CNY'], b['operating_profit_CNY'])

    def test_signed_expense_reversal_and_negative_operating_profit_are_preserved(self):
        a = self.snapshot([self.report(admin='-5.00')])['records'][0]
        self.assertEqual(a['operating_profit_CNY'], '35.00')
        self.assertEqual(Decimal(a['operating_profit_to_lagged_assets']), Decimal('.35'))
        b = self.snapshot([self.report(cost='100.00')])['records'][0]
        self.assertEqual(b['operating_profit_CNY'], '-15.00')
        self.assertEqual(Decimal(b['operating_profit_to_lagged_assets']), Decimal('-.15'))

    def test_ten_thousand_yuan_units_normalize_without_changing_ratio(self):
        row = self.snapshot([self.report(unit='万元')])['records'][0]
        self.assertEqual(row['operating_profit_CNY'], '250000.00')
        self.assertEqual(row['lagged_assets_CNY'], '1000000.00')
        self.assertEqual(Decimal(row['operating_profit_to_lagged_assets']), Decimal('.25'))

    def test_missing_or_duplicate_expense_not_zero_filled_or_taken_from_parent(self):
        for replacement in ('', '管理费用 七、64 5.00 2.00\n管理费用 七、64 5.00 2.00\n'):
            data = source()
            data[2] = data[2].replace('管理费用 七、64 5.00 2.00\n', replacement)
            data[3] += '管理费用 1.00 2.00\n'
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                op.parse_report(data, 2023)
        data = source();data[2] = data[2].replace('研发费用 七、65 7.00 6.00\n', '')
        with self.assertRaises(ValueError):op.parse_report(data, 2023)

    def test_extra_columns_unknown_units_wrong_currency_and_parent_scope_are_rejected(self):
        changes = [lambda p:[t.replace('5.00 2.00', '5.00 2.00 1.00') for t in p],
                   lambda p:[t.replace('人民币', '美元') for t in p],
                   lambda p:[t.replace('单位:元', '单位:百万元') for t in p],
                   lambda p:[*p, p[2]], lambda p:[t.replace('2023年度 2022年度', '2022年度 2023年度') for t in p],
                   lambda p:[t.replace('100.00\n', '0.00\n') if i == 0 else t for i,t in enumerate(p)]]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):op.parse_report(change(source()), 2023)

    def test_generic_or_January1_opening_cannot_become_lagged_December31_assets(self):
        for header in ('项目 期末余额 期初余额', '项目 附注 2023年12月31日 2023年1月1日'):
            data = source();data[0] = data[0].replace('项目 附注 2023年12月31日 2022年12月31日', header)
            with self.subTest(header=header), self.assertRaises(ValueError):op.parse_report(data, 2023)

    def test_same_page_multiline_row_supported_but_cross_page_value_is_not(self):
        data = source();data[2] = data[2].replace('管理费用 七、64 5.00 2.00', '管理费用\n七、64\n5.00\n2.00')
        self.assertEqual(op.parse_report(data, 2023)['income']['2023-12-31']['administrative_expenses']['value_CNY'], '5.00')
        data = source();data[2] = data[2].replace('管理费用 七、64 5.00 2.00\n', '') + '管理费用\n'
        data.insert(3, '5.00 2.00\n')
        with self.assertRaises(ValueError):op.parse_report(data, 2023)

    def test_record_validation_rejects_changed_literal_scope_column_header_and_amount(self):
        parsed = op.parse_report(source(), 2023)
        for name,value in [('value_CNY','50.00'),('statement','母公司利润表'),('column_index',1),
                           ('fiscal_end','2022-12-31'),('header_line','项目 附注 2022年度 2021年度')]:
            bad = copy.deepcopy(parsed);bad['income']['2023-12-31']['administrative_expenses'][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                op.make_report('SH600001',2023,'2024-04-27','2026-10-23T00:00:00+00:00','a'*64,'123456',bad)

    def test_default_observed_mode_and_explicit_publication_end_boundary(self):
        record = self.report()
        self.assertEqual(op.snapshot_reports([record], '2025-12-31T15:05:00+08:00')['records'], [])
        self.assertEqual(self.snapshot([record], '2024-04-27T23:59:59+08:00')['records'], [])
        self.assertEqual(len(self.snapshot([record], '2024-04-28T00:00:00+08:00')['records']), 1)
        self.assertEqual(len(op.snapshot_reports([record], '2026-10-23T00:00:00+00:00')['records']), 1)
        with self.assertRaises(ValueError):op.snapshot_reports([record], '2024-12-31T00:00:00')
        with self.assertRaises(ValueError):self.report(publication='2023-12-31')

    def test_future_payload_cannot_be_hashed_validated_or_used_in_earlier_snapshot(self):
        old = self.report();future = self.report(2024, '2025-04-26', doc='b')
        future['payload'] = object()
        self.assertEqual(self.snapshot([old, future]), self.snapshot([old]))
        with self.assertRaises((ValueError, TypeError)):
            self.snapshot([old, future], '2025-05-01T00:00:00+08:00')

    def test_all_supported_editions_remain_separate_and_duplicate_conflicts_fail_closed(self):
        old = self.report();new = self.report(2024, '2025-04-26', doc='b')
        result = self.snapshot([new, old, copy.deepcopy(old)], '2025-05-01T00:00:00+08:00')
        self.assertEqual([r['fiscal_end'] for r in result['records']], ['2023-12-31','2024-12-31'])
        with self.assertRaises(ValueError):self.snapshot([old,self.report(doc='b')])


if __name__ == '__main__':
    unittest.main()
