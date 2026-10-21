"""Identity QA must follow cover/issuer scope, not unrelated report codes."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-22-profitability-all1236-v6-source-cells.py'
spec=importlib.util.spec_from_file_location('profitability_v6_separate_qa',path)
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)


class SeparateSourceIdentityTests(unittest.TestCase):
    def test_cover_code_precedes_other_codes_in_the_first20_pages(self):
        pages=['公司代码：600001\n2024年年度报告',*['']*4,'证券代码：600002']
        result=qa.source_identity(pages,'SH600001',2024)
        self.assertTrue(result['code_consistent']);self.assertTrue(result['annual_year_consistent'])
        self.assertEqual(result['code_selection_scope'],'FIRST5_COVER')
        self.assertEqual([e['code'] for e in result['literal_code_evidence']],['600001'])
        self.assertEqual([e['code'] for e in result['other_literal_codes_retained_for_context']],['600001','600002'])

    def test_missing_cover_code_needs_bounded_issuer_information_context(self):
        pages=['2024年年度报告',*['']*4,'一、公司信息\n证券代码：600001']
        result=qa.source_identity(pages,'SH600001',2024)
        self.assertTrue(result['code_consistent']);self.assertEqual(result['code_selection_scope'],'FIRST20_ISSUER_INFORMATION')
        self.assertEqual(result['literal_code_evidence'][0]['context'],'一、公司信息\n证券代码：600001')
        pages[-1]='其他事项\n证券代码：600001'
        self.assertFalse(qa.source_identity(pages,'SH600001',2024)['code_consistent'])

    def test_A_share_information_table_and_spaced_annual_title_are_literal_evidence(self):
        header='股票种类 股票上市交易所 股票简称 股票代码 变更前股票简称'
        pages=['2 0 2 4 年 年 度 报 告',*['']*4,header+'\nA股 上海证券交易所 测试 600001 无']
        result=qa.source_identity(pages,'SH600001',2024)
        self.assertTrue(result['code_consistent']);self.assertTrue(result['annual_year_consistent'])
        self.assertEqual(result['literal_code_evidence'][0]['context'],'ISSUER_STOCK_INFORMATION_TABLE')
        pages[-1]+=' 600002'
        self.assertFalse(qa.source_identity(pages,'SH600001',2024)['code_consistent'])

    def test_wrong_year_or_code_outside_first20_cannot_establish_identity(self):
        pages=['2023年年度报告',*['']*19,'一、公司信息\n证券代码：600001']
        result=qa.source_identity(pages,'SH600001',2024)
        self.assertFalse(result['code_consistent']);self.assertFalse(result['annual_year_consistent'])


class SeparateFiscalHeaderTests(unittest.TestCase):
    def test_repeated_header_on_consolidated_continuation_pages_is_valid(self):
        header='项目 2024年度 2023年度'
        qa.verify_source_header(header,108,lambda p:header,[(108,header),(109,header)])

    def test_parent_page_cannot_supply_consolidated_header_even_with_same_text(self):
        header='项目 2024年度 2023年度'
        with self.assertRaises(AssertionError):qa.verify_source_header(header,110,lambda p:header,[(108,header),(109,'其他行')])

    def test_header_must_be_an_exact_source_block_not_part_of_a_longer_line(self):
        header='项目 2024年度 2023年度'
        with self.assertRaises(AssertionError):qa.verify_source_header(header,108,lambda p:'其他'+header,[(108,header)])


if __name__=='__main__':unittest.main()
