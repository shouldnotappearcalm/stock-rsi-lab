import copy
import unittest

try:
    from stock_rsi import operating_source_bridge as bridge
except ImportError:
    bridge=None
from stock_rsi.data import digest
from stock_rsi import annual_operating as op
from tests.test_asset_geometry import real_inputs,parse
from tests.test_annual_operating import source
from tests.test_profitability_availability import document


def synthetic_inputs():
    doc=document(2023,'2024-04-29','1');doc.update(effective_fiscal_year=2023)
    texts=source(2023,cost='60.00',admin='-5.00')
    texts.append('主要会计数据和财务指标\n2023年末 2022年末 2021年末\n总资产（元） 200.00 100.00 80.00\n')
    cell=op.grammar.parse_consolidated_tables(texts,2023)["2023-12-31"]['total_assets']
    def word(text,x,y,width=45):return {'text':text,'x0':x,'x1':x+width,'top':y,'bottom':y+8}
    pages=[{'physical_page':5,'width':600,'height':800,'source_sha256':doc['source_sha256'],
        'tables':[{'bbox':[10,10,590,150]}],'words':[
            word('2023年末',170,30),word('2022年末',320,30),word('2021年末',470,30),
            word('总资产（元）',20,70,80),word('200.00',170,70),word('100.00',320,70),word('80.00',470,70)]},
        {'physical_page':cell['page'],'width':600,'height':800,'source_sha256':doc['source_sha256'],
         'tables':[{'bbox':[10,10,590,150]}],'words':[word('资产总计',20,70,80),word('200.00',170,70),word('100.00',320,70)]}]
    return doc,texts,pages,cell


class OperatingSourceBridgeTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(bridge,'separate operating source bridge module missing')

    def test_synthetic_signed_source_composition_preserves_origins_clocks_and_all_income_fields(self):
        doc,texts,pages,cell=synthetic_inputs()
        record=bridge.recover_source_record(doc,texts,pages,cell,normative_basis=bridge.geometry.NORMATIVE_BASIS)
        self.assertEqual(record['contract'],bridge.CONTRACT);self.assertEqual(record['record_id'],digest({k:v for k,v in record.items() if k!='record_id'}))
        self.assertEqual(record['payload']['income']['2023-12-31']['administrative_expenses']['value_CNY'],'-5.00')
        self.assertEqual(record['payload']['income']['2022-12-31']['research_expenses']['value_CNY'],'6.00')
        self.assertEqual(record['payload']['asset_bridge']['prior']['value_CNY'],'100.00')
        self.assertEqual(record['observed_at'],doc['captured_at_utc'])
        self.assertFalse(record['investment_factor_admitted']);self.assertNotIn('operating_profit_to_lagged_assets',str(record))

    def test_missing_expense_wrong_document_and_capture_clock_reject_source_record(self):
        for mode in ('research','source','clock'):
            doc,texts,pages,cell=synthetic_inputs()
            if mode=='research':texts[2]=texts[2].replace('研发费用 七、65 7.00 6.00\n','')
            elif mode=='source':doc['source_sha256']='f'*64
            else:doc['captured_at_utc']='2023-01-01T00:00:00+00:00'
            with self.subTest(mode=mode),self.assertRaises(ValueError):bridge.recover_source_record(doc,texts,pages,cell,normative_basis=bridge.geometry.NORMATIVE_BASIS)

    def test_geometry_pages_and_words_must_exist_in_authenticated_cached_text(self):
        for mode in ('page','literal'):
            doc,texts,pages,cell=synthetic_inputs()
            if mode=='page':texts=texts[:4]
            else:texts[4]=texts[4].replace('2022年末','2019年末')
            with self.subTest(mode=mode),self.assertRaises(ValueError):bridge.recover_source_record(doc,texts,pages,cell,normative_basis=bridge.geometry.NORMATIVE_BASIS)

    def test_coverage_uses_only_original_visible_selection_and_never_exposes_amounts(self):
        view={'as_of':'2024-01-01T15:05:00+08:00','visibility_mode':op.RECONSTRUCTED,'cohort_count':3,
          'classifications':[{'instrument':'SH600001','annual_status':'NO_VISIBLE_ANNUAL_REPORT'},
            {'instrument':'SH600002','annual_status':'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'},
            {'instrument':'SH600003','annual_status':'LATEST_OPERATING_SOURCE_SCHEMA_UNSUPPORTED','selected_capture_key':'new','selected_source_sha256':'a'*64}]}
        calls=[]
        def reader(key):
            calls.append(key);self.assertEqual(key,'new')
            return {'capture_key':key,'instrument':'SH600003','source_sha256':'a'*64,'effective_source_status':'STILL_UNSUPPORTED','effective_record_id':None}
        result=bridge.augment_coverage(view,reader)
        self.assertEqual(calls,['new']);self.assertEqual(len(result['classifications']),3)
        self.assertEqual(result['classifications'][-1]['effective_source_status'],'STILL_UNSUPPORTED')
        self.assertNotIn('value_CNY',str(result));self.assertNotIn('effective_source_status',view['classifications'][-1])
        view['classifications'][-1]['selected_source_sha256']='b'*64
        with self.assertRaises(ValueError):bridge.augment_coverage(view,reader)


if __name__=='__main__':unittest.main()
