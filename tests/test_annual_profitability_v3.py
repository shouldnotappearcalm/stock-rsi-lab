import json
from pathlib import Path
import unittest

from stock_rsi import annual_profitability as original
from stock_rsi import annual_profitability_v3 as grammar


def pages():
    return ['公司代码：600001\n2022年年度报告', '''二、财务报表
财务附注中报表的单位为：人民币元
1、合并资产负债表
单位：元
项目 2022年12月31日 2021年12月31日
资产总计 200.00 100.00
''', '2、母公司资产负债表\n资产总计 999.00 888.00', '''3
、合并利润表
单位：元
项目
2022
年度
2021
年度
其中：营业收入
100.00
80.00
其中：营业成本
70.00
60.00
''', '4、母公司利润表\n营业收入 999.00 888.00',
            '三、公司基本情况\n合并利润表\n营业收入 999999.00 999999.00\n母公司利润表']


class AnnualProfitabilityV3Tests(unittest.TestCase):
    def test_primary_section_prevents_notes_tables_from_overriding_main_statements(self):
        data = grammar.parse_consolidated_tables(pages(), 2022)
        self.assertEqual(data['2022-12-31']['revenue']['value_CNY'], '100.00')
        self.assertEqual(data['2021-12-31']['cost_of_sales']['value_CNY'], '60.00')
        cell = data['2022-12-31']['revenue']
        self.assertEqual(cell['row_text'], '其中：营业收入\n100.00\n80.00')
        self.assertEqual(cell['currency_scope_evidence'][0]['page'], 2)
        self.assertEqual(cell['financial_section_context']['end_page_exclusive'], 6)

    def test_real_report_preparation_currency_and_exact_current_comparative_cells(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/annual-profitability-v3-real-context-excerpts.json').read_text())
        self.assertFalse(fixture['CI_fetches_or_authenticates_original_PDF'])
        physical = [''] * fixture['physical_page_count']
        for page, evidence in fixture['sparse_page_excerpts'].items():
            physical[int(page)-1] = evidence['text']
        cells = grammar.parse_consolidated_tables(physical, fixture['report_year'])
        self.assertEqual({p: {f: c['value_CNY'] for f,c in fields.items()} for p,fields in cells.items()}, fixture['expected_cells_CNY'])
        self.assertEqual(cells['2022-12-31']['revenue']['currency_scope_evidence'][0]['page'], 100)
        for period, data in cells.items():
            record = original.make_observation(fixture['instrument'], fixture['report_year'], period,
                fixture['publication_day'], fixture['observed_at'], fixture['source_pdf_sha256'],
                fixture['announcement_id'], data)
            self.assertEqual(original.snapshot_observations([record], '2024-12-31T15:05:00+08:00')['records'], [])

    def test_prior_two_source_fixtures_keep_all_original_numeric_cells(self):
        directory = Path(__file__).parent / 'fixtures'
        old = json.loads((directory / 'annual-profitability-real-row-vintages.json').read_text())
        for d in old['documents']:
            physical = [''] * d['physical_page_count']
            for page,text in d['page_excerpts'].items():
                physical[int(page)-1] = text
            data = grammar.parse_consolidated_tables(physical, d['report_year'])
            self.assertEqual({p: {f:c['value_CNY'] for f,c in fields.items()} for p,fields in data.items()}, d['expected_cells_CNY'])
        d = json.loads((directory / 'annual-profitability-v2-real-multiline-note-excerpts.json').read_text())
        physical = [''] * d['physical_page_count']
        for page,e in d['sparse_page_excerpts'].items():
            physical[int(page)-1] = e['text']
        data = grammar.parse_consolidated_tables(physical, d['report_year'])
        self.assertEqual({p: {f:c['value_CNY'] for f,c in fields.items()} for p,fields in data.items()}, d['expected_cells_CNY'])

    def test_functional_currency_alone_wrong_currency_or_outside_section_unit_is_insufficient(self):
        for replacement in ('本公司采用人民币为记账本位币。',
                            '财务附注中报表的单位为：美元元', ''):
            changed = [p.replace('财务附注中报表的单位为：人民币元', replacement) for p in pages()]
            changed[-1] += '\n财务附注中报表的单位为：人民币元'
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                grammar.parse_consolidated_tables(changed, 2022)

    def test_missing_cross_page_and_extra_vertical_amounts_fail_without_borrowing(self):
        for before, after in [('100.00\n80.00', '100.00'),
                              ('100.00\n80.00', '100.00\n80.00\n90.00'),
                              ('100.00\n80.00', '100.00\n80.00\n其中：营业收入\n1.00\n2.00'),
                              ('2021\n年度', '2021\n年度\n2020年度')]:
            with self.subTest(after=after), self.assertRaises(ValueError):
                grammar.parse_consolidated_tables([p.replace(before, after) for p in pages()], 2022)
        changed = pages()
        changed[3] = changed[3].replace('100.00\n80.00', '100.00')
        changed.insert(4, '80.00')
        with self.assertRaises(ValueError):
            grammar.parse_consolidated_tables(changed, 2022)

    def test_missing_ambiguous_or_unbounded_primary_section_and_duplicate_main_tables_fail(self):
        variants = [pages() + ['二、财务报表'],
                    [p.replace('三、公司基本情况', '不明边界') for p in pages()],
                    pages()[:3] + [pages()[3]] + pages()[3:],
                    pages()[:5] + [''] * 41 + pages()[5:]]
        for changed in variants:
            with self.assertRaises(ValueError):
                grammar.parse_consolidated_tables(changed, 2022)

    def test_issuer_cover_precedes_unrelated_company_codes_in_body(self):
        p = pages() + ['证券代码：600002']
        identity = grammar.document_identity(p, 'SH600001', 2022)
        self.assertTrue(identity['code_consistent'])
        self.assertEqual(identity['code_selection_scope'], 'FIRST5_COVER')
        self.assertEqual(len(identity['other_literal_codes_retained_for_context']), 2)
        p[0] = '公司代码：600002\n2022年度报告'
        p[5] += '\n一、公司信息\n股票代码：600001'
        self.assertFalse(grammar.document_identity(p, 'SH600001', 2022)['code_consistent'])

    def test_issuer_stock_table_identity_and_spaced_annual_title(self):
        p = ['2 0 2 2 年 年 度 报 告'] + [''] * 5 + ['''五、公司股票简况
公司股票简况
股票种类 股票上市交易所 股票简称 股票代码 变更前股票简称
A股 上海证券交易所 示例公司 600001 不适用''']
        identity = grammar.document_identity(p, 'SH600001', 2022)
        self.assertTrue(identity['code_consistent'])
        self.assertTrue(identity['annual_year_consistent'])
        self.assertFalse(grammar.document_identity(p, 'SH600002', 2022)['code_consistent'])
        self.assertFalse(grammar.document_identity(p, 'SH600001', 2023)['annual_year_consistent'])

    def test_current_fiscal_order_unknown_units_and_financial_proxies_stay_rejected(self):
        for before, after in [('2022年12月31日 2021年12月31日', '2021年12月31日 2022年12月31日'),
                              ('单位：元', '单位：百万元'),
                              ('其中：营业成本', '二、营业总支出'),
                              ('其中：营业收入', '一、营业总收入')]:
            with self.subTest(after=after), self.assertRaises(ValueError):
                grammar.parse_consolidated_tables([p.replace(before,after) for p in pages()], 2022)

    def test_opening_balance_date_is_retained_without_fabricating_prior_year_gp(self):
        changed = [p.replace('2021年12月31日', '2022年1月1日') for p in pages()]
        data = grammar.parse_consolidated_tables(changed, 2022)
        self.assertEqual(set(data), {'2022-12-31'})
        cell = data['2022-12-31']['total_assets']
        self.assertEqual(cell['value_CNY'], '200.00')
        self.assertEqual(cell['reported_comparative_balance_date'], '2022-01-01')
        self.assertIn('100.00', cell['row_text'])


if __name__ == '__main__':
    unittest.main()
