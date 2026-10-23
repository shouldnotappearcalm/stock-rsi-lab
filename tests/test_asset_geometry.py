import copy
import json
from pathlib import Path
import unittest

try:
    from stock_rsi import asset_geometry as mapper
except ImportError:
    mapper=None
from stock_rsi.data import digest

FIXTURE=Path(__file__).parent/'fixtures/operating-asset-summary-real-word-geometry.json'


def real_inputs(index=0):
    d=json.loads(FIXTURE.read_text())['documents'][index]
    pages=[{'physical_page':p['physical_page'],'width':p['width'],'height':p['height'],
            'source_sha256':d['source_pdf_sha256'],'tables':p['relevant_raw_tables'],'words':p['words']} for p in d['source_pages']]
    current,opening=d['expected_summary_current_literal'],d['expected_summary_prior_literal']
    row='资产总计 '+current+' '+opening
    primary={'source_sha256':d['source_pdf_sha256'],'report_year':d['fiscal_year'],'cell':{
        'statement':'合并资产负债表','fiscal_end':f'{d["fiscal_year"]}-12-31','column_index':0,
        'page':d['consolidated_asset_band']['page'],'row_text':row,'row_text_sha256':digest(row),
        'unit':'元','unit_evidence_literal':d['original_consolidated_source_unit_literal'],
        'literal':current,'value_CNY':current.replace(',',''),'header_line':d['original_consolidated_source_header'],
        'reported_comparative_balance_date':d['original_consolidated_comparative_date']}}
    return d,pages,primary


def parse(d,pages,primary,**kwargs):
    return mapper.parse_summary_assets(pages,d['fiscal_year'],d['publication_day'],d['source_pdf_sha256'],primary,
        normative_basis=kwargs.get('normative_basis',mapper.NORMATIVE_BASIS))


def edit_words(pages,predicate,change):
    for page in pages:
        for word in page['words']:
            if predicate(page,word):change(word)


class AssetGeometryTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(mapper,'source word asset mapper missing')

    def test_all_four_original_editions_select_exact_year_adjustment_and_preserve_opening_date(self):
        for index in range(4):
            d,pages,primary=real_inputs(index);result=parse(d,pages,primary)
            with self.subTest(key=d['capture_key']):
                self.assertEqual(result['current']['literal'],d['expected_summary_current_literal'])
                self.assertEqual(result['prior']['literal'],d['expected_summary_prior_literal'])
                self.assertEqual(result['prior']['fiscal_end'],f'{d["fiscal_year"]-1}-12-31')
                self.assertEqual(result['primary_comparative_date_as_reported'],d['original_consolidated_comparative_date'])
                self.assertEqual(result['prior']['adjustment'],'AFTER_ADJUSTMENT' if index<2 else 'AS_REPORTED')
                self.assertEqual(sum(map(len,result['columns_by_year'].values())),(5,5,4,3)[index])
                self.assertTrue(result['currency_is_regulatory_inference']);self.assertFalse(result['investment_factor_admitted'])
                self.assertNotIn('ratio',result);self.assertEqual(result['record_id'],digest({k:v for k,v in result.items() if k!='record_id'}))

    def test_input_word_order_and_fragmented_default_grid_rows_do_not_select_columns(self):
        d,pages,primary=real_inputs(2);expected=parse(d,pages,primary);mutated=copy.deepcopy(pages)
        for page in mutated:
            page['words'].reverse()
            for table in page['tables']:table['rows']=[['forged default row','999.00']]
        self.assertEqual(parse(d,mutated,primary),expected)
        self.assertEqual(expected['prior']['fiscal_end'],'2023-12-31')
        self.assertEqual(expected['columns_by_year']['2022'][1]['adjustment'],'AFTER_ADJUSTMENT')

    def test_swapped_year_and_adjustment_headers_cannot_choose_values_by_matching_primary(self):
        for mode in ('year','adjustment'):
            d,pages,primary=real_inputs(0)
            if mode=='year':
                edit_words(pages,lambda p,w:w['text'] in ('2022年末','2021年末'),
                    lambda w:w.update(text={'2022年末':'2021年末','2021年末':'2022年末'}[w['text']]))
            else:
                edit_words(pages,lambda p,w:w['text'] in ('调整前','调整后'),
                    lambda w:w.update(text={'调整前':'调整后','调整后':'调整前'}[w['text']]))
            with self.subTest(mode=mode),self.assertRaises(ValueError):parse(d,pages,primary)

    def test_missing_adjustment_or_prior_year_header_is_not_inferred(self):
        for text in ('调整前','调整后','2021年末'):
            d,pages,primary=real_inputs(0)
            for p in pages:p['words']=[w for w in p['words'] if w['text']!=text]
            with self.subTest(text=text),self.assertRaises(ValueError):parse(d,pages,primary)

    def test_percentage_or_duplicate_money_is_not_a_valid_asset_column(self):
        for mode in ('percent','duplicate','missing'):
            d,pages,primary=real_inputs(0)
            p=next(p for p in pages if p['physical_page']==10)
            if mode=='percent':
                next(w for w in p['words'] if w['text']=='7.01%')['text']='7.01'
            elif mode=='duplicate':p['words'].append(copy.deepcopy(next(w for w in p['words'] if w['text']==d['expected_summary_prior_literal'])))
            else:p['words']=[w for w in p['words'] if w['text']!=d['expected_summary_prior_literal']]
            with self.subTest(mode=mode),self.assertRaises(ValueError):parse(d,pages,primary)

    def test_other_edition_primary_unit_amount_and_source_corruption_fail(self):
        for field,value in [('source_sha256','f'*64),('report_year',2021),('value_CNY','1.00'),('unit','万元')]:
            d,pages,primary=real_inputs()
            (primary if field in ('source_sha256','report_year') else primary['cell'])[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):parse(d,pages,primary)

    def test_cross_page_header_gaps_width_changes_and_duplicate_pages_fail(self):
        for mode in ('gap','width','duplicate','source'):
            d,pages,primary=real_inputs(0)
            if mode=='gap':next(p for p in pages if p['physical_page']==9)['physical_page']=8
            elif mode=='width':next(p for p in pages if p['physical_page']==9)['width']+=20
            elif mode=='source':pages[0]['source_sha256']='f'*64
            else:pages.append(copy.deepcopy(pages[0]))
            with self.subTest(mode=mode),self.assertRaises(ValueError):parse(d,pages,primary)

    def test_nonfinite_outside_and_boolean_geometry_fail(self):
        for value in (float('nan'),-100,True,10000):
            d,pages,primary=real_inputs();pages[0]['words'][0]['x0']=value
            with self.subTest(value=value),self.assertRaises(ValueError):parse(d,pages,primary)

    def test_currency_rule_missing_forged_later_version_and_foreign_label_fail(self):
        d,pages,primary=real_inputs()
        for basis in (None,{**mapper.NORMATIVE_BASIS,'body_sha256':'f'*64}):
            with self.subTest(basis=basis),self.assertRaises(ValueError):parse(d,pages,primary,normative_basis=basis)
        changed=copy.deepcopy(d);changed['publication_day']='2025-07-01'
        with self.assertRaises(ValueError):parse(changed,pages,primary)
        edit_words(pages,lambda p,w:w['text']=='总资产（元）',lambda w:w.update(text='总资产（美元）'))
        with self.assertRaises(ValueError):parse(d,pages,primary)

    def test_duplicate_year_anchor_or_other_currency_inside_governing_table_fails(self):
        for mode in ('duplicate','foreign'):
            d,pages,primary=real_inputs(2);p=next(p for p in pages if p['physical_page']==9)
            word=copy.deepcopy(next(w for w in p['words'] if w['text']=='2023年末'))
            word.update(text='2023年末' if mode=='duplicate' else '币种:美元',x0=word['x0']+2,x1=word['x1']+2)
            p['words'].append(word)
            with self.subTest(mode=mode),self.assertRaises(ValueError):parse(d,pages,primary)


if __name__=='__main__':unittest.main()
