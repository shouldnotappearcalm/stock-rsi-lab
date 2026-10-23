from copy import deepcopy
from pathlib import Path
import json
from unittest import TestCase
try:
    from stock_rsi import annual_cash_accruals_v2 as v2
except ImportError:v2=None
from stock_rsi import annual_cash_accruals as v1
from stock_rsi.data import digest
from tests.test_annual_cash_accruals import source,DOC

ROW='四、净利润（净亏损以“－”号填列） 七、68 -5.00 3.00'
def wrapped(lines=None):
    p=source();p[2]=p[2].replace(ROW,lines or '四、净利润（净亏损以“－”号填\n列） 七、68 -5.00 3.00');return p

class AnnualCashAccrualV2Tests(TestCase):
    def setUp(self):self.assertIsNotNone(v2,'wrapped caption source adapter missing')
    def report(self,pages=None):return v2.make_report(DOC,v2.parse_report(pages or wrapped(),2023))
    def test_four_original_row_witnesses_recover_eight_hand_checked_cells(self):
        f=json.loads((Path(__file__).parent/'fixtures/annual-cash-accrual-wrapped-real-rows.json').read_text());self.assertFalse(f['CI_authenticates_original_PDF']);self.assertEqual(len(f['documents']),4)
        for d in f['documents']:
            table=deepcopy(d['original_income_table']);table['metadata']['parser_contract']=v2.CONTRACT;y=d['document']['effective_fiscal_year'];values=v2.net_profit_cells(table,y)
            for i,literal in enumerate(d['hand_checked_net_profit_literals']):
                c=values[f'{y-i}-12-31'];self.assertEqual(c['literal'],literal);self.assertEqual(c['value_CNY'],literal.replace(',',''));self.assertEqual(c['page'],d['original_PDF_row_page']);self.assertEqual(c['normalization_rule'],'APPROVED_CAPTION_WHITESPACE_ONLY');self.assertEqual(c['row_text_sha256'],digest(c['row_text']))
    def test_two_and_eight_line_caption_preserve_negative_values_and_source(self):
        for text in ['四、净利润（净亏损以“－”号填\n列） 七、68 -5.00 3.00','四、净利润（净亏损以\n“\n－\n”\n号填\n列）\n-5.00\n3.00']:
            p=wrapped(text);r=self.report(p);c=r['parsed']['income']['2023-12-31']['net_profit'];self.assertEqual(c['value_CNY'],'-5.00');self.assertEqual(c['row_text'],text);self.assertEqual(r['contract'],v2.CONTRACT);v2.verify_source_tables(r['parsed'],p,2023)
    def test_original_v1_reports_and_digests_are_preserved_identically(self):
        p=source();old=v1.make_report(DOC,v1.parse_report(p,2023));self.assertEqual(self.report(p),old);self.assertEqual(v2.parse_report(p,2023),old['parsed'])
    def test_twelve_line_boundary_supported_thirteen_cross_page_or_missing_rejected(self):
        lines=['四、净利润','（','净亏损','以','“','－','”','号','填','列）','-5.00','3.00'];self.assertEqual(len(lines),12);self.assertEqual(self.report(wrapped('\n'.join(lines)))['parsed']['income']['2023-12-31']['net_profit']['value_CNY'],'-5.00')
        for text in ['\n'.join(lines).replace('列）','列\n）'),'四、净利润（净亏损以“－”号填\n列） 七、68 -5.00','四、净利润（净亏损以“－”号填\n列） 七、68 — 3.00']:
            with self.subTest(text=text),self.assertRaises(ValueError):self.report(wrapped(text))
        p=wrapped('四、净利润（净亏损以“－”号填\n列） 七、68 -5.00');p[3]='3.00\n'+p[3]
        with self.assertRaises(ValueError):self.report(p)
    def test_digits_signs_and_decimal_tokens_in_tail_are_never_joined(self):
        for tail in ['1,\n000.00 3.00','-\n5.00 3.00','5.\n00 3.00','-5.00 3.00 9.00','-5.00 3.00\n9.00']:
            with self.subTest(tail=tail),self.assertRaises(ValueError):self.report(wrapped('四、净利润（净亏损以“－”号填\n列） 七、68 '+tail))
    def test_duplicate_preheader_parent_attributable_or_child_row_cannot_rescue(self):
        text='四、净利润（净亏损以“－”号填\n列） 七、68 -5.00 3.00'
        for mode in ('duplicate','preheader','parent','continuing','attributable'):
            p=wrapped(text)
            if mode=='duplicate':p[2]=p[2].replace(text,text+'\n'+text)
            if mode=='preheader':p[2]=p[2].replace(text,'').replace('项目 附注 2023年度 2022年度',text+'\n项目 附注 2023年度 2022年度')
            if mode=='parent':p[2]=p[2].replace(text,'');p[3]+='\n'+text
            if mode=='continuing':p[2]=p[2].replace(text,text.replace('四、净利润','1.持续经营净利润'))
            if mode=='attributable':p[2]=p[2].replace(text,text.replace('四、净利润','归属于母公司股东的净利润'))
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.report(p)
    def test_caption_offset_contract_and_source_provenance_tampering_rejected(self):
        for key,value in [('caption_end_offset',999),('normalized_caption','归母净利润'),('normalization_rule','REMOVE_ALL_WHITESPACE'),('literal','999.00'),('header_occurrences',[{'page':99,'literal':'wrong'}])]:
            r=self.report();r['parsed']['income']['2023-12-31']['net_profit'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v2.make_report(DOC,r['parsed'])
        r=self.report();r['parsed']['tables']['balances']['metadata']['parser_contract']='UNKNOWN'
        with self.assertRaises(ValueError):v2.make_report(DOC,r['parsed'])
    def test_both_contracts_gate_future_loaders_and_validate_visible_report(self):
        calls=[]
        def poison():calls.append(1);raise AssertionError('future monetary callback')
        for mode,at in [(v2.RECONSTRUCTED,'2024-04-27T15:05:00+08:00'),(v2.OBSERVED,'2025-12-31T15:05:00+08:00')]:self.assertIsNone(v2.visible_report(DOC,at,poison,mode))
        self.assertEqual(calls,[])
        for r in (self.report(),self.report(source())):self.assertEqual(v2.visible_report(DOC,'2024-04-28T15:05:00+08:00',lambda:r,v2.RECONSTRUCTED),r)
        with self.assertRaises(ValueError):v2.visible_report(DOC,'2024-04-28T15:05:00',poison,v2.RECONSTRUCTED)
        self.assertEqual(calls,[])
