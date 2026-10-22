import copy
import unittest

try:
    from stock_rsi import annual_assets as assets
except ImportError:
    assets=None

from stock_rsi.data import digest
from tests.test_annual_profitability import pages
from tests import test_annual_profitability_v6 as cas_fixture


class AnnualAssetsTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(assets,'standalone annual-assets source module missing')

    def parse(self,source):return assets.parse_balance_only(source,2023,normative_basis=assets.CAS19_REFERENCE)

    def report(self,balances=None):
        return assets.make_report('SH600001',2023,'2024-04-27','2026-10-22T00:00:00+00:00',
            'a'*64,'123456',balances or self.parse(pages()))

    def test_balances_do_not_depend_on_income_revenue_cost_or_income_currency_cells(self):
        source=pages();source[2]='合并利润表\n单位:美元\n收入布局无法识别\n';source[3]='母公司利润表\n'
        parsed=self.parse(source)
        self.assertEqual(set(parsed),{'2023-12-31','2022-12-31'})
        self.assertEqual(parsed['2023-12-31']['value_CNY'],'200.00')
        self.assertEqual(parsed['2022-12-31']['value_CNY'],'100.00')
        self.assertEqual(parsed['2022-12-31']['column_index'],1)
        self.assertEqual(parsed['2023-12-31']['statement'],'合并资产负债表')
        self.assertEqual(parsed['2023-12-31']['page'],1)

    def test_generic_undated_opening_is_current_only_and_needs_literal_current_date(self):
        source=pages();source[0]=source[0].replace('项目 附注 2023年12月31日 2022年12月31日','项目 期末余额 期初余额')
        balances=self.parse(source);self.assertEqual(set(balances),{'2023-12-31'})
        self.assertIsNone(balances['2023-12-31']['reported_comparative_balance_date'])
        self.assertTrue(balances['2023-12-31']['comparative_date_is_unresolved'])
        source[0]=source[0].replace('2023 年12月31日\n','')
        with self.assertRaises(ValueError):self.parse(source)

    def test_explicit_Jan1_is_not_a_prior_December31(self):
        source=[s.replace('2022年12月31日','2023年1月1日') for s in pages()]
        balances=self.parse(source);self.assertEqual(set(balances),{'2023-12-31'})
        self.assertEqual(balances['2023-12-31']['reported_comparative_balance_date'],'2023-01-01')

    def test_balance_scope_currency_units_duplicate_and_extra_columns_fail_closed(self):
        changes=[lambda p:p[1:]+[p[0]],lambda p:[p[0],p[1],p[0],*p[2:]],
            lambda p:[s.replace('资产总计 七、1 200.00 100.00','资产总计 七、1 200.00 100.00 80.00') for s in p],
            lambda p:[s.replace('200.00 100.00','200.00 -100.00') for s in p],
            lambda p:[p[0].replace('单位:元 币种:人民币','单位:元\n币种:美元'),*p[1:]],
            lambda p:[p[0].replace('单位:元 币种:人民币','单位:美元'),*p[1:]],
            lambda p:[p[0].replace('单位:元 币种:人民币','单位:元'),*p[1:]],
            lambda p:[s.replace('2023年12月31日 2022年12月31日','2022年12月31日 2023年12月31日') for s in p]]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):self.parse(change(pages()))

    def test_same_scoped_CAS_currency_inference_stays_labelled_and_pinned(self):
        source=cas_fixture.AnnualProfitabilityV6Tests().source()
        balances=self.parse(source)
        evidence=balances['2023-12-31']['currency_scope_evidence'][0]
        self.assertTrue(evidence['currency_is_regulatory_inference_not_literal_quote'])
        with self.assertRaises(ValueError):assets.parse_balance_only(source,2023)

    def test_coherent_report_preserves_source_cells_without_mutating_inputs(self):
        cells=self.parse(pages());original=copy.deepcopy(cells);r=self.report(cells)
        self.assertEqual(r['payload']['balances'],cells);self.assertEqual(cells,original)
        self.assertEqual(r['payload']['scope'],'CONSOLIDATED')
        self.assertEqual(r['payload']['document_sha256'],'a'*64)
        self.assertEqual(r['public_day_end_at'],'2024-04-27T15:59:59.999999+00:00')
        self.assertEqual(r['record_id'],digest({k:v for k,v in r.items() if k!='record_id'}))
        self.assertFalse(r['investment_factor_admitted'])

    def test_missing_current_wrong_date_cell_value_or_row_digest_cannot_make_report(self):
        good=self.parse(pages())
        for change in [lambda b:b.pop('2023-12-31'),
                       lambda b:b['2022-12-31'].update(column_index=0),
                       lambda b:b['2022-12-31'].update(reported_comparative_balance_date='2023-01-01'),
                       lambda b:b['2023-12-31'].update(value_CNY='999.00'),
                       lambda b:b['2023-12-31'].update(row_text_sha256='0'*64)]:
            bad=copy.deepcopy(good);change(bad)
            with self.subTest(change=change),self.assertRaises(ValueError):self.report(bad)

    def test_observed_and_reconstruction_visibility_keep_all_editions_without_future_payload_read(self):
        r=self.report()
        self.assertEqual(assets.visible_reports([r],'2025-12-31T15:05:00+08:00')['reports'],[])
        before=assets.visible_reports([r],'2024-04-27T23:59:59.999998+08:00',mode=assets.RECONSTRUCTED)
        self.assertEqual(before['reports'],[])
        at=assets.visible_reports([r],'2024-04-27T23:59:59.999999+08:00',mode=assets.RECONSTRUCTED)
        self.assertEqual(at['reports'],[r])
        hidden=copy.deepcopy(r);hidden['payload']=object()
        self.assertEqual(assets.visible_reports([hidden],'2025-12-31T15:05:00+08:00')['reports'],[])
        changed=copy.deepcopy(r);changed['payload']['balances']['2023-12-31']['value_CNY']='999.00'
        with self.assertRaises(ValueError):assets.visible_reports([changed],'2025-12-31T15:05:00+08:00',mode=assets.RECONSTRUCTED)
        with self.assertRaises(ValueError):assets.visible_reports([r],'2024-01-01')


if __name__=='__main__':unittest.main()
