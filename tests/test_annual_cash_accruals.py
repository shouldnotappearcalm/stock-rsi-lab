from copy import deepcopy
from unittest import TestCase
try:
    from stock_rsi import annual_cash_accruals as cash
except ImportError:cash=None
from tests.test_annual_profitability import pages
from stock_rsi.data import digest

DOC={'instrument':'SH600001','effective_fiscal_year':2023,'day':'2024-04-27','captured_at_utc':'2026-10-23T00:00:00+00:00','source_sha256':'a'*64,'announcement_id':'123456','capture_key':'SH600001-2023-123456'}
def source(unit='元',profit='-5.00',cfo='20.00'):
    p=pages(unit=unit);p[2]+=f'四、净利润（净亏损以“－”号填列） 七、68 {profit} 3.00\n归属于母公司所有者的净利润 999.00 888.00\n'
    p.extend([f'合并现金流量表\n2023年1—12月\n单位:{unit} 币种:人民币\n项目 附注 2023年度 2022年度\n经营活动产生的现金流量净额 七、69 {cfo} -2.00\n', '母公司现金流量表\n经营活动产生的现金流量净额 999.00 888.00\n']);return p

class AnnualCashAccrualTests(TestCase):
    def setUp(self):self.assertIsNotNone(cash,'cash-accrual source adapter missing')
    def report(self):return cash.make_report(DOC,cash.parse_report(source(),2023))
    def test_same_edition_signed_consolidated_cells_are_not_attributable_profit(self):
        v=cash.parse_report(source(),2023);self.assertEqual(v['income']['2023-12-31']['net_profit']['value_CNY'],'-5.00');self.assertEqual(v['cashflows']['2023-12-31']['operating_cashflow']['value_CNY'],'20.00');self.assertEqual(v['cashflows']['2022-12-31']['operating_cashflow']['value_CNY'],'-2.00');self.assertEqual(v['balances']['2022-12-31']['value_CNY'],'100.00');r=cash.make_report(DOC,v);self.assertEqual(r['record_id'],digest({k:v for k,v in r.items() if k!='record_id'}));self.assertFalse(r['investment_factor_admitted']);self.assertNotIn('score',r)
    def test_source_units_normalize_both_statements(self):
        v=cash.parse_report(source('万元'),2023);self.assertEqual(v['income']['2023-12-31']['net_profit']['value_CNY'],'-50000.00');self.assertEqual(v['cashflows']['2023-12-31']['operating_cashflow']['value_CNY'],'200000.00')
    def test_missing_parent_only_blank_duplicate_and_extra_cells_fail(self):
        for index,text in [(2,'四、净利润（净亏损以“－”号填列） 七、68 -5.00 3.00\n'),(4,'经营活动产生的现金流量净额 七、69 20.00 -2.00\n')]:
            for replacement in ('',text+text,text.replace('20.00 -2.00','20.00 -2.00 1.00').replace('-5.00 3.00','-5.00 3.00 1.00'),text.replace('20.00 -2.00','— -2.00').replace('-5.00 3.00','— 3.00')):
                p=source();p[index]=p[index].replace(text,replacement)
                with self.subTest(index=index,replacement=replacement),self.assertRaises(ValueError):cash.parse_report(p,2023)
    def test_wrong_period_currency_or_duplicate_statement_fails(self):
        cases=[lambda p:[t.replace('2022年12月31日','2023年1月1日') for t in p],lambda p:[t.replace('币种:人民币','币种:美元') for t in p],lambda p:p+[p[4]],lambda p:[t.replace('项目 附注 2023年度 2022年度','项目 附注 2023年度 2022年度 2021年度') for t in p]]
        for change in cases:
            with self.subTest(change=change),self.assertRaises(ValueError):cash.parse_report(change(source()),2023)
    def test_report_rejects_literal_unit_period_and_digest_tampering(self):
        for field,value in [('value_CNY','999.00'),('literal','999.00'),('column_index',1),('fiscal_end','2022-12-31'),('statement','母公司利润表'),('unit','万元'),('row_text_sha256','b'*64)]:
            v=cash.parse_report(source(),2023);v['income']['2023-12-31']['net_profit'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):cash.make_report(DOC,v)
        report=self.report();report['record_id']='b'*64
        with self.assertRaises(ValueError):cash.visible_report(DOC,'2024-04-28T15:05:00+08:00',lambda:report,cash.RECONSTRUCTED)
    def test_public_day_end_and_observed_clock_gate_before_monetary_loader(self):
        calls=[]
        def poison():calls.append(1);raise AssertionError('future monetary report')
        for mode,at in [(cash.RECONSTRUCTED,'2024-04-26T23:59:59+08:00'),(cash.RECONSTRUCTED,'2024-04-27T15:05:00+08:00'),(cash.OBSERVED,'2025-12-31T23:59:59+08:00')]:self.assertIsNone(cash.visible_report(DOC,at,poison,mode))
        self.assertEqual(calls,[]);r=self.report();self.assertEqual(cash.visible_report(DOC,'2024-04-28T15:05:00+08:00',lambda:r,cash.RECONSTRUCTED),r)
        for at,mode in [('2024-04-28T15:05:00',cash.RECONSTRUCTED),('2024-04-28T15:05:00+08:00','UNKNOWN')]:
            with self.assertRaises(ValueError):cash.visible_report(DOC,at,poison,mode)
        self.assertEqual(calls,[])
    def test_visible_metadata_source_and_report_must_be_one_edition(self):
        r=self.report()
        for key,value in [('source_sha256','b'*64),('announcement_id','456'),('day','2024-04-26'),('instrument','SZ000001')]:
            d={**DOC,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):cash.visible_report(d,'2024-04-28T15:05:00+08:00',lambda:r,cash.RECONSTRUCTED)

    def test_pre_header_summary_cannot_replace_missing_table_body_row(self):
        p=source();row='四、净利润（净亏损以“－”号填列） 七、68 -5.00 3.00\n';p[2]=p[2].replace(row,'').replace('项目 附注 2023年度 2022年度',row+'项目 附注 2023年度 2022年度')
        with self.assertRaises(ValueError):cash.parse_report(p,2023)
    def test_complete_header_row_and_location_provenance_must_agree(self):
        for kind in ('header','row','unit_location','header_occurrences'):
            p=cash.parse_report(source(),2023);cells=p['income']
            if kind=='header':
                for cell in cells.values():cell['net_profit']['header_line']='WRONG 2021年度 附注 2023年度 2022年度'
            cell=cells['2022-12-31']['net_profit']
            if kind=='row':cell.update(row_text=cell['row_text'].replace('3.00','999.00'),literal='999.00',value_CNY='999.00');cell['row_text_sha256']=digest(cell['row_text'])
            if kind=='unit_location':cell['unit_evidence_page']=-999
            if kind=='header_occurrences':cell['header_occurrences']=[{'page':999,'literal':'garbage'}]
            with self.subTest(kind=kind),self.assertRaises(ValueError):cash.make_report(DOC,p)
