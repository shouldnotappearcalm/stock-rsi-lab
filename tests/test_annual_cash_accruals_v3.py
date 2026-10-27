from copy import deepcopy
import json
from pathlib import Path
from unittest import TestCase
from stock_rsi import annual_cash_accruals_v3 as v3
from stock_rsi import annual_cash_accruals_v2 as v2
from tests.test_annual_cash_accruals import DOC,source
from tests.test_annual_cash_accruals_v2 import wrapped

CFO='经营活动产生的现金流量净额 七、69 20.00 -2.00'
def pages(tail='20.00 -2.00'):
    p=wrapped();p[4]=p[4].replace(CFO,'经营活动产生的现金流\n量净额 七、69 '+tail);return p

class CashAccrualV3Tests(TestCase):
    def report(self,p=None):return v3.make_report(DOC,v3.parse_report(p or pages(),2023))
    def test_signed_cfo_and_ni_are_recovered_without_changing_amounts(self):
        r=self.report();self.assertEqual(r['contract'],v3.CONTRACT)
        self.assertEqual(r['parsed']['cashflows']['2023-12-31']['operating_cashflow']['value_CNY'],'20.00')
        self.assertEqual(r['parsed']['cashflows']['2022-12-31']['operating_cashflow']['value_CNY'],'-2.00')
        self.assertEqual(r['parsed']['income']['2023-12-31']['net_profit']['value_CNY'],'-5.00')
        v3.verify_source_tables(r['parsed'],pages(),2023)
    def test_all_original_v1_and_v2_successful_reports_stay_identical(self):
        for p in (source(),wrapped()):self.assertEqual(v3.make_report(DOC,v3.parse_report(p,2023)),v2.make_report(DOC,v2.parse_report(p,2023)))
    def test_numeric_digits_signs_unknown_and_extra_cells_never_normalized(self):
        for tail in ('2\\n0.00 -2.00','-\\n20.00 -2.00','20.00 —','20.00 -2.00 7.00','20.00 -2.00\\n7.00 8.00'):
            tail=tail.replace('\\n','\n')
            with self.subTest(tail=tail),self.assertRaises(ValueError):self.report(pages(tail))
    def test_parent_duplicate_preheader_and_wrong_caption_do_not_rescue(self):
        label='经营活动产生的现金流\n量净额 七、69 20.00 -2.00'
        for mode in ('parent','duplicate','header','investment'):
            p=pages()
            if mode=='parent':p[4]=p[4].replace(label,'');p[5]+='\n'+label
            if mode=='duplicate':p[4]+='\n'+label
            if mode=='header':p[4]=p[4].replace(label,'').replace('项目 附注',label+'\n项目 附注')
            if mode=='investment':p[4]=p[4].replace('经营活动产生的现金流\n量净额','投资活动产生的现金流\n量净额')
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.report(p)
    def test_cross_page_and_caption_offset_tampering_fail(self):
        p=pages();p[4]=p[4].replace('量净额 七、69 20.00 -2.00','');p[5]='量净额 七、69 20.00 -2.00\n'+p[5]
        with self.assertRaises(ValueError):self.report(p)
        r=self.report();r['parsed']['cashflows']['2023-12-31']['operating_cashflow']['caption_end_offset']=0
        with self.assertRaises(ValueError):v3.make_report(DOC,r['parsed'])

    def test_original_cfo_page128_matches_two_hand_checked_values(self):
        f=json.loads((Path(__file__).parent/'fixtures/annual-cash-accrual-cfo-real-row.json').read_text())
        self.assertFalse(f['CI_authenticates_original_PDF']);t=deepcopy(f['original_cashflow_table']);t['metadata']['parser_contract']=v3.CONTRACT
        cells=v3.wrapped_cells(t,2022,'cashflows')
        for i,literal in enumerate(f['hand_checked_CFO_literals']):
            c=cells[f'{2022-i}-12-31'];self.assertEqual(c['literal'],literal);self.assertEqual(c['value_CNY'],literal.replace(',',''));self.assertEqual(c['page'],128)
