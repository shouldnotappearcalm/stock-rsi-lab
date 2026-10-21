import json
from pathlib import Path
import unittest

from stock_rsi import annual_profitability_v5 as grammar
from tests.test_annual_profitability import pages


class AnnualProfitabilityV5Tests(unittest.TestCase):
    def bare(self, declaration='本公司编制本财务报表时所采用的货币为人民币。', note='61'):
        result = [p.replace('单位:元 币种:人民币','单位:元').replace('七、61',note)
                  for p in pages()]
        result.append('4、记账本位币\n'+declaration)
        return result

    def test_old_successes_are_returned_without_changed_cells_or_metadata(self):
        self.assertEqual(grammar.parse_consolidated_tables(pages(),2023),
                         grammar.prior.parse_consolidated_tables(pages(),2023))

    def test_currency_declaration_and_local_unit_are_separate_source_evidence(self):
        data = grammar.parse_consolidated_tables(self.bare(),2023)
        cell = data['2023-12-31']['revenue']
        self.assertEqual(cell['value_CNY'],'100.00')
        self.assertEqual(cell['unit'],'元')
        self.assertEqual(cell['unit_evidence_literal'],'单位:元')
        self.assertEqual(cell['currency_scope_evidence'][0]['currency'],'CNY')
        self.assertNotIn('unit',cell['currency_scope_evidence'][0])
        self.assertEqual(cell['currency_scope_evidence'][0]['literal'],'本公司编制本财务报表时所采用的货币为人民币。')
        for declaration in ('本集团编制本财务报表时所采用的货币为人民币。','本财务报表以人民币列示。',
                            '本公司记账本位币和编制本财务报表所采用的货币均为人民币。',
                            '本公司编制本财务报表时所采用的\n货币为人民币。'):
            with self.subTest(declaration=declaration):
                self.assertEqual(grammar.parse_consolidated_tables(self.bare(declaration),2023)['2023-12-31']['total_assets']['value_CNY'],'200.00')

    def test_functional_currency_foreign_currency_and_long_or_cross_page_quotes_do_not_qualify(self):
        for declaration in ('本公司采用人民币为记账本位币。','本集团以人民币为记账本位币。',
                            '本公司编制本财务报表时所采用的货币为美元。',
                            '本公司编制本财务报表时所采用的货币为人民币。\n本财务报表以港币列示。',
                            '本公司编制本\n财务报\n表时所采\n用的货\n币为人民币。'):
            with self.subTest(declaration=declaration), self.assertRaises(ValueError):
                grammar.parse_consolidated_tables(self.bare(declaration),2023)
        source=self.bare('本公司编制本财务报表时所采用的货币为')
        source.append('人民币。')
        with self.assertRaises(ValueError): grammar.parse_consolidated_tables(source,2023)

    def test_note_alias_requires_header_and_exact_two_monetary_cells(self):
        for note in ('61','七/61'):
            with self.subTest(note=note):
                data=grammar.parse_consolidated_tables(self.bare(note=note),2023)
                self.assertEqual(data['2023-12-31']['revenue']['value_CNY'],'100.00')
                self.assertIn(note,data['2023-12-31']['revenue']['row_text'])
        for note in ('0','1000','7/61','61.00','61 1.00'):
            with self.subTest(note=note), self.assertRaises(ValueError):
                grammar.parse_consolidated_tables(self.bare(note=note),2023)
        no_header=[p.replace('项目 附注','项目') for p in self.bare()]
        with self.assertRaisesRegex(ValueError,'explicit note column header'):
            grammar.parse_consolidated_tables(no_header,2023)
        third=[p.replace('100.00 80.00','100.00 80.00\n1.00') for p in self.bare()]
        with self.assertRaisesRegex(ValueError,'extra monetary continuation'):
            grammar.parse_consolidated_tables(third,2023)

    def test_local_unit_aliases_keep_original_evidence_and_multiplier(self):
        for unit in ('单位：人民币元','编制单位:某公司 单位:元 币种:人民币',
                     '编制单位：某公司2023年度 单位：人民币元','(金额单位：人民币元)',
                     '（除特别注明外，金额单位均为人民币元）'):
            with self.subTest(unit=unit):
                source=[p.replace('单位:元 币种:人民币',unit) for p in pages()]
                cell=grammar.parse_consolidated_tables(source,2023)['2023-12-31']['total_assets']
                self.assertEqual(cell['value_CNY'],'200.00')
                self.assertEqual(cell['unit_evidence_literal'],unit)
        source=[p.replace('单位:元 币种:人民币','单位：人民币万元') for p in pages()]
        self.assertEqual(grammar.parse_consolidated_tables(source,2023)['2023-12-31']['total_assets']['value_CNY'],'2000000.00')
        for unit in ('单位：美元元','单位：人民币百万元','单位：人民币元 单位：人民币万元',
                     '编制单位：某公司单位：美元元单位：元币种：人民币'):
            with self.subTest(unit=unit), self.assertRaises(ValueError):
                grammar.parse_consolidated_tables([p.replace('单位:元 币种:人民币',unit) for p in pages()],2023)

    def test_opening_balance_period_and_total_cost_exclusion_remain(self):
        source=[p.replace('2022年12月31日','2023年1月1日') for p in self.bare()]
        self.assertEqual(set(grammar.parse_consolidated_tables(source,2023)),{'2023-12-31'})
        for before,after in [('其中：营业收入','营业总收入'),('其中：营业成本','营业总成本')]:
            with self.subTest(after=after), self.assertRaises(ValueError):
                grammar.parse_consolidated_tables([p.replace(before,after) for p in self.bare()],2023)

    def test_real_currency_and_unit_excerpts_match_reviewed_source_formats(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/annual-profitability-v5-source-format-excerpts.json').read_text())
        for record in fixture['records']:
            if 'expected_currency_only_declaration_count' in record:
                source=['']*(record['physical_page']-1)+[record['source_excerpt']]
                result=grammar.reporting_currency(source)
                self.assertEqual(len(result),record['expected_currency_only_declaration_count'])
                self.assertEqual(result[0]['page'],record['physical_page'])
            elif 'expected_local_unit' in record:
                self.assertEqual(grammar.explicit_local_unit(record['local_unit_literal']),record['expected_local_unit'])


if __name__ == '__main__': unittest.main()
