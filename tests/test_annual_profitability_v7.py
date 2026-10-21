import json
from pathlib import Path
import unittest
from stock_rsi import annual_profitability_v7 as grammar
from stock_rsi import annual_profitability_v6 as old
from tests.test_annual_profitability import pages


class AnnualProfitabilityV7Tests(unittest.TestCase):
    def generic(self,year=2024):
        source=pages(year)
        source[0]=source[0].replace(f'项目 附注 {year}年12月31日 {year-1}年12月31日','项目 期末余额 期初余额')
        return source

    def parse(self,source,year=2024):
        try:return grammar.parse_consolidated_tables(source,year,normative_basis=old.CAS19_REFERENCE)
        except ValueError as e:self.fail('source-backed format must parse: '+str(e))

    def reject(self,source,year=2024):
        with self.assertRaises(ValueError):grammar.parse_consolidated_tables(source,year,normative_basis=old.CAS19_REFERENCE)

    def test_old_successes_keep_complete_cells_and_evidence_identical(self):
        self.assertEqual(grammar.parse_consolidated_tables(pages(),2023),old.parse_consolidated_tables(pages(),2023))

    def test_generic_balance_admits_only_explicitly_anchored_current_date(self):
        result=self.parse(self.generic());self.assertEqual(set(result),{'2024-12-31'})
        cell=result['2024-12-31']['total_assets']
        self.assertEqual(cell['value_CNY'],'200.00');self.assertEqual(cell['column_index'],0)
        self.assertEqual(cell['header_line'],'项目 期末余额 期初余额')
        self.assertIsNone(cell['reported_comparative_balance_date'])
        self.assertTrue(cell['comparative_date_is_unresolved'])
        self.assertEqual(cell['balance_current_date_anchor']['literal'],'2024 年12月31日')
        self.assertTrue(cell['current_column_date_is_inferred_from_explicit_statement_date'])
        self.assertEqual(cell['row_text'],'资产总计 七、1 200.00 100.00')

    def test_missing_wrong_quarterly_duplicate_or_parent_only_date_cannot_anchor_current(self):
        for replacement in ['', '2023 年12月31日\n','2024 年6月30日\n','2024 年12月31日\n2024 年12月31日\n']:
            source=self.generic();source[0]=source[0].replace('2024 年12月31日\n',replacement)
            with self.subTest(replacement=replacement):self.reject(source)
        source=self.generic();source[0]=source[0].replace('2024 年12月31日\n','');source[1]='2024 年12月31日\n'+source[1];self.reject(source)

    def test_generic_column_order_income_years_and_extra_columns_remain_strict(self):
        for before,after in [('期末余额 期初余额','期初余额 期末余额'),('期末余额 期初余额','期末余额 期初余额 调整前'),
                             ('2024年度 2023年度','本期发生额 上期发生额'),('200.00 100.00','200.00 100.00 90.00')]:
            with self.subTest(after=after):self.reject([s.replace(before,after) for s in self.generic()])

    def test_chapter_note_header_aliases_preserve_literal_dates_and_monetary_cells(self):
        for label in ['附注七','附注（七）','附注(七)']:
            source=[s.replace('项目 附注 ','项目 '+label+' ') for s in pages(2024)]
            result=self.parse(source)
            self.assertEqual(set(result),{'2024-12-31','2023-12-31'})
            self.assertEqual(result['2023-12-31']['cost_of_sales']['value_CNY'],'60.00')
            self.assertIn(label,result['2024-12-31']['revenue']['header_line'])

    def test_long_same_page_split_calendar_header_is_exact_not_a_year_guess(self):
        source=pages(2024)
        source[0]=source[0].replace('项目 附注 2024年12月31日 2023年12月31日','项目\n附注\n2024\n年\n12\n月\n31\n日\n2023\n年\n12\n月\n31\n日')
        result=self.parse(source);self.assertEqual(set(result),{'2024-12-31','2023-12-31'})
        self.assertIn('\n',result['2024-12-31']['total_assets']['header_line'])
        source[0]=source[0].replace('\n2023\n年\n12\n月\n31\n日','\n2024\n年\n1\n月\n1\n日')
        result=self.parse(source);self.assertEqual(set(result),{'2024-12-31'})
        self.assertEqual(result['2024-12-31']['total_assets']['reported_comparative_balance_date'],'2024-01-01')

    def continuation(self):
        source=self.generic();source[2]=source[2].replace('其中：营业成本 70.00 60.00\n','')
        source.insert(3,'项目 附注 2024年度 2023年度\n其中：营业成本 70.00 60.00\n')
        return source

    def test_identical_header_on_later_consolidated_page_is_valid_continuation(self):
        result=self.parse(self.continuation());cell=result['2024-12-31']['cost_of_sales']
        self.assertEqual(cell['value_CNY'],'70.00');self.assertEqual(cell['page'],4)
        self.assertEqual([e['page'] for e in cell['header_occurrences']],[3,4])

    def test_same_page_or_conflicting_continuation_header_is_ambiguous(self):
        source=self.continuation();source[2]+=source.pop(3);self.reject(source)
        for replacement in ['项目 附注 2024年度 2022年度','项目 附注 2023年度 2024年度','项目 附注 2024年度 2023年度 2022年度']:
            source=self.continuation();source[3]=source[3].replace('项目 附注 2024年度 2023年度',replacement);self.reject(source)

    def test_foreign_currency_financial_proxies_missing_CAS_and_unbounded_headers_reject(self):
        for before,after in [('人民币','美元'),('其中：营业收入','营业总收入'),('其中：营业成本','营业总成本')]:
            with self.subTest(after=after):self.reject([s.replace(before,after) for s in self.generic()])
        self.reject([s.replace('单位:元 币种:人民币','单位:元') for s in self.generic()])
        source=self.generic();source[0]=source[0].replace('项目 期末余额 期初余额','项目\n'+'未知\n'*21+'期末余额\n期初余额');self.reject(source)


    def test_original_reviewed_header_excerpts_preserve_generic_and_calendar_semantics(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/annual-profitability-v7-header-format-excerpts.json').read_text())
        for r in fixture['records']:
            selected=[(r['physical_page'],s) for s in r['source_lines_before_and_in_header']]
            found=grammar.headers(selected,r['fiscal_year'],r['income_table'])
            self.assertEqual(found[0]['literal'],r['source_header_literal'])
            self.assertEqual(found[0]['kind'],r['expected_header_semantics'])
            self.assertEqual(found[0]['comparison'],r['expected_comparative_balance_date'])
            if found[0]['kind']=='GENERIC_CURRENT_AND_UNDATED_OPENING':
                date=grammar.current_date_anchor(selected,found[0],r['fiscal_year'])
                self.assertEqual(date['date'],'2024-12-31')


    def test_generic_current_observation_keeps_capture_and_publication_visibility_separate(self):
        source=[s.replace('单位:元 币种:人民币','单位:元') for s in self.generic()]
        source.append('1、遵循企业会计准则的声明\n本财务报表符合企业会计准则的要求，真实、完整地反映了公司的财务状况。')
        cells=self.parse(source)['2024-12-31']
        self.assertTrue(cells['total_assets']['currency_scope_evidence'][0]['currency_is_regulatory_inference_not_literal_quote'])
        record=grammar.original.make_observation('SH600001',2024,'2024-12-31','2025-04-27',
            '2026-10-22T00:00:00+00:00','a'*64,'123456',cells)
        self.assertEqual(grammar.original.snapshot_observations([record],'2025-05-01T15:05:00+08:00')['records'],[])
        conditional=grammar.original.snapshot_observations([record],'2025-05-01T15:05:00+08:00',mode=grammar.original.RECONSTRUCTED)
        self.assertEqual([r['fiscal_end'] for r in conditional['records']],['2024-12-31'])
        self.assertFalse(conditional['investment_factor_admitted'])


if __name__=='__main__':unittest.main()
