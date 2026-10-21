import copy
import json
from pathlib import Path
import unittest

from stock_rsi import annual_profitability as old
from stock_rsi import annual_profitability_v2 as new


def pages():
    return ['''二、财务报表
财务附注中报表的单位为：人民币元
1、合并资产负债表
单位：元
项目 2022年12月31
日
2021年12月31
日
资产总计 七、（三） 200.00 100.00
''', '2、母公司资产负债表\n资产总计 999.00 999.00', '''3、合并利润表
单位:元 币种:人民币
项目 附注 2022年度 2021年度
其中：营业收入 七 (61) 100.00 80.00
其中：营业成本 七、（六十一） 70.00 60.00
''', '4、母公司利润表\n营业收入 999.00 999.00\n营业成本 1.00 1.00']


class AnnualProfitabilityV2Tests(unittest.TestCase):
    def test_preexisting_original_real_row_numeric_results_are_preserved(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/annual-profitability-real-row-vintages.json').read_text())
        for document in fixture['documents']:
            physical = [''] * document['physical_page_count']
            for page, text in document['page_excerpts'].items():
                physical[int(page) - 1] = text
            original = old.parse_consolidated_tables(physical, document['report_year'])
            revised = new.parse_consolidated_tables(physical, document['report_year'])
            for period, fields in original.items():
                for field, cell in fields.items():
                    self.assertEqual(cell['value_CNY'], revised[period][field]['value_CNY'])
                    self.assertEqual(cell['page'], revised[period][field]['page'])

    def test_bounded_numbered_titles_multiline_columns_and_explicit_notes(self):
        cells = new.parse_consolidated_tables(pages(), 2022)
        self.assertEqual(cells['2022-12-31']['total_assets']['value_CNY'], '200.00')
        self.assertEqual(cells['2021-12-31']['cost_of_sales']['value_CNY'], '60.00')
        self.assertEqual(cells['2022-12-31']['revenue']['parser_contract'], new.CONTRACT)
        self.assertEqual(cells['2022-12-31']['total_assets']['unit_evidence_scope'],
                         'LOCAL_FINANCIAL_SECTION_EXPLICIT_RMB')
        with self.assertRaises(ValueError):
            old.parse_consolidated_tables(pages(), 2022)

    def test_real_multiline_note_excerpt_matches_visually_reviewed_original_cells(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/annual-profitability-v2-real-multiline-note-excerpts.json').read_text())
        self.assertFalse(fixture['CI_fetches_or_authenticates_original_PDF'])
        physical = [''] * fixture['physical_page_count']
        for page, evidence in fixture['sparse_page_excerpts'].items():
            physical[int(page) - 1] = evidence['text']
        cells = new.parse_consolidated_tables(physical, fixture['report_year'])
        self.assertEqual({p: {f: c['value_CNY'] for f, c in fields.items()} for p, fields in cells.items()},
                         fixture['expected_cells_CNY'])
        for period, data in cells.items():
            record = old.make_observation(fixture['instrument'], fixture['report_year'], period,
                fixture['publication_day'], fixture['observed_at'], fixture['source_pdf_sha256'],
                fixture['announcement_id'], data)
            self.assertEqual([], old.snapshot_observations([record], '2024-12-31T15:05:00+08:00')['records'])

    def test_missing_wrong_or_remote_currency_evidence_is_not_guessed(self):
        for change in (
            lambda p: [x.replace('财务附注中报表的单位为：人民币元', '') for x in p],
            lambda p: [x.replace('人民币', '美元') for x in p],
            lambda p: ['财务附注中报表的单位为：人民币元', *[x.replace('财务附注中报表的单位为：人民币元', '') for x in p]],
            lambda p: [x.replace('单位：元', '单位：万元') for x in p],
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                new.parse_consolidated_tables(change(pages()), 2022)

    def test_wrong_extra_and_reversed_fiscal_columns_are_rejected(self):
        for before, after in (
            ('2022年度 2021年度', '2021年度 2022年度'),
            ('2022年度 2021年度', '2022年度 2021年度 2020年度'),
            ('2022年度 2021年度\n', '2022年度 2021年度\n2020年度\n'),
            ('2021年12月31\n日', '2020年12月31\n日'),
            ('200.00 100.00', '200.00 100.00 90.00'),
        ):
            with self.subTest(after=after), self.assertRaises(ValueError):
                new.parse_consolidated_tables([x.replace(before, after) for x in pages()], 2022)

    def test_ambiguous_notes_missing_cells_and_financial_proxies_are_rejected(self):
        for before, after in (
            ('七 (61) 100.00 80.00', '61 100.00 80.00'),
            ('七 (61) 100.00 80.00', '不明附注 100.00 80.00'),
            ('70.00 60.00', '70.00'),
            ('其中：营业成本', '二、营业总支出'),
            ('其中：营业收入', '一、营业总收入'),
        ):
            with self.subTest(after=after), self.assertRaises(ValueError):
                new.parse_consolidated_tables([x.replace(before, after) for x in pages()], 2022)

    def test_duplicate_consolidated_heading_or_row_and_missing_parent_boundary_fail(self):
        for changed in (pages() + [pages()[2]],
                        [x.replace('其中：营业收入', '其中：营业收入 七、61 1.00 2.00\n其中：营业收入') for x in pages()],
                        [x.replace('4、母公司利润表', '非报表标题') for x in pages()]):
            with self.assertRaises(ValueError):
                new.parse_consolidated_tables(changed, 2022)

    def test_original_visible_snapshot_cannot_be_replaced_by_later_v2_comparative(self):
        cells = new.parse_consolidated_tables(pages(), 2022)
        source = old.make_observation('SH600001', 2022, '2022-12-31', '2023-04-29',
            '2026-10-22T00:00:00+00:00', 'a' * 64, '1234', cells['2022-12-31'])
        future = copy.deepcopy(source)
        future['public_day_end_at'] = '2025-04-30T15:59:59.999999+00:00'
        future['payload'] = {'bad_future_data': object()}
        before = old.snapshot_observations([source], '2024-12-31T15:05:00+08:00', mode=old.RECONSTRUCTED)
        self.assertEqual(before, old.snapshot_observations([source, future], before['as_of'], mode=old.RECONSTRUCTED))

    def test_identity_literal_separator_bounded_window_and_conflict(self):
        p = ['2022年度报告'] + [''] * 18 + ['证券代码｜ 600001']
        self.assertTrue(new.document_identity(p, 'SH600001', 2022)['code_consistent'])
        self.assertFalse(new.document_identity([*p[:19], '', p[-1]], 'SH600001', 2022)['code_consistent'])
        self.assertTrue(new.document_identity([*p, '证券代码:600002'], 'SH600001', 2022)['code_consistent'])
        p[1] = '股票代码：600002'
        self.assertFalse(new.document_identity(p, 'SH600001', 2022)['code_consistent'])
        self.assertFalse(new.document_identity(['2022年度报告\n公司代码:600001234'], 'SH600001', 2022)['code_consistent'])
        self.assertTrue(new.document_identity(['证券代码：600001\n2022年度报告'], 'SH600001', 2022)['code_consistent'])


if __name__ == '__main__':
    unittest.main()
