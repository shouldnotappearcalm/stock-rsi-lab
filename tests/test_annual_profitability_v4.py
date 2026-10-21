import json
from pathlib import Path
import unittest

from stock_rsi import annual_profitability_v3 as v3
from stock_rsi import annual_profitability_v4 as v4
from tests.test_annual_profitability_v3 import pages


class AnnualProfitabilityV4Tests(unittest.TestCase):
    def test_real_printed_page_number_does_not_swallow_unnumbered_statement(self):
        directory = Path(__file__).parent / 'fixtures'
        boundary = json.loads((directory / 'annual-profitability-v4-page-number-boundary.json').read_text())
        source = json.loads((directory / 'annual-profitability-v2-real-multiline-note-excerpts.json').read_text())
        self.assertEqual(boundary['source_pdf_sha256'], source['source_pdf_sha256'])
        physical = [''] * source['physical_page_count']
        for page, e in source['sparse_page_excerpts'].items():
            physical[int(page)-1] = e['text']
        physical[boundary['physical_page']-1] = boundary['printed_page_number'] + '\n' + physical[boundary['physical_page']-1]
        with self.assertRaises(ValueError):
            v3.parse_consolidated_tables(physical, 2022)
        data = v4.parse_consolidated_tables(physical, 2022)
        self.assertEqual({p: {f:c['value_CNY'] for f,c in fields.items()} for p,fields in data.items()}, source['expected_cells_CNY'])

    def test_numbered_heading_split_requires_literal_enumeration_separator(self):
        self.assertEqual(v4.source_lines(['84\n合并利润表']), [(1, '84'), (1, '合并利润表')])
        self.assertEqual(v4.source_lines(['3\n、合并利润表']), [(1, '3\n、合并利润表')])
        self.assertEqual(v4.source_lines(['3、\n合并利润表']), [(1, '3、\n合并利润表')])
        self.assertEqual(v4.source_lines(['3', '、合并利润表']), [(1, '3'), (2, '、合并利润表')])

    def test_v3_context_numeric_results_and_current_only_opening_date_are_preserved(self):
        for physical in (pages(), [p.replace('2021年12月31日', '2022年1月1日') for p in pages()]):
            before, after = v3.parse_consolidated_tables(physical, 2022), v4.parse_consolidated_tables(physical, 2022)
            self.assertEqual(set(before), set(after))
            for period, fields in before.items():
                for field, cell in fields.items():
                    self.assertEqual(cell['value_CNY'], after[period][field]['value_CNY'])
                    self.assertEqual(after[period][field]['parser_contract'], v4.CONTRACT)


if __name__ == '__main__':
    unittest.main()
