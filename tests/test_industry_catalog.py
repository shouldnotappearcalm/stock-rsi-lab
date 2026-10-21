import copy
import json
from pathlib import Path
import unittest
from stock_rsi import industry_catalog as catalog


HEADER=['门类名称及代码','行业大类代码','行业大类名称','上市公司代码','上市公司简称']
SHA='c'*64
PUBLIC='2021-12-27T20:06:27+00:00'
OBSERVED='2026-10-22T00:00:00+00:00'


def packet(number,body):
    values=[HEADER,*body];rows=[]
    for i,values_row in enumerate(values):
        cells=[]
        for j,value in enumerate(values_row):
            if value is None:box=None
            else:
                end=i+1
                if i and j<3:
                    end=next((k for k in range(i+1,len(values)) if values[k][j] is not None),len(values))
                box=[10+j*100,20+i*20,110+j*100,20+end*20]
            cells.append({'literal':value,'bbox':box})
        rows.append({'row_index':i,'cells':cells})
    return {'physical_page':number,'source_sha256':SHA,'width':600,'height':800,
            'tables':[{'table_index':0,'bbox':[10,20,510,20+len(values)*20],'rows':rows}]}


def bundle():
    source=packet(1,[['农、林、牧、渔业\n(A)','01','农业','000998','隆平高科'],
                     [None,None,None,'002041','登海种业'],
                     ['金融业\n(J)','67','资本市场服务','600030','中信证券']])
    return catalog.parse_catalog([source],source_sha256=SHA,public_by=PUBLIC,observed_at=OBSERVED,expected_pages=1)


class IndustryCatalogTests(unittest.TestCase):
    def parse(self,packets):
        return catalog.parse_catalog(packets,source_sha256=SHA,public_by=PUBLIC,observed_at=OBSERVED,expected_pages=len(packets))

    def test_merged_geometry_keeps_literal_code_name_and_original_field_origin(self):
        result=bundle();rows=result['records'];self.assertEqual(len(rows),3)
        self.assertEqual(rows[1]['stock_code'],'002041');self.assertEqual(rows[1]['sector_code'],'A')
        self.assertEqual(rows[1]['industry_code'],'01');self.assertEqual(rows[1]['stock_name'],'登海种业')
        self.assertEqual(rows[1]['field_sources']['sector']['row_index'],1)
        self.assertEqual(rows[1]['field_sources']['stock_code']['row_index'],2)
        self.assertEqual(rows[1]['inherited_fields'],['sector','industry_code','industry_name'])
        self.assertEqual(rows[2]['sector_code'],'J');self.assertEqual(rows[2]['sector_name'],'金融业')
        self.assertFalse(result['current_business_identity_verified'])

    def test_ordered_page_continuation_can_carry_context_and_new_minor_group_replaces_it(self):
        first=packet(1,[['农、林、牧、渔业(A)','01','农业','000998','隆平高科']])
        second=packet(2,[[None,None,None,'002041','登海种业'],[None,'02','林业','000592','平潭发展']])
        rows=self.parse([first,second])['records']
        self.assertEqual(rows[1]['sector_code'],'A');self.assertTrue(rows[1]['classification_context_carried_across_pages'])
        self.assertEqual(rows[2]['industry_code'],'02');self.assertEqual(rows[2]['field_sources']['industry_code']['physical_page'],2)
        self.assertEqual(rows[2]['field_sources']['sector']['physical_page'],1)

    def test_new_major_cannot_inherit_an_old_minor_code_or_conflicting_major_name(self):
        for last in [['金融业(J)',None,None,'600030','中信证券'],['另一个行业(A)','02','林业','000592','平潭发展']]:
            with self.subTest(last=last),self.assertRaises(ValueError):
                self.parse([packet(1,[['农、林、牧、渔业(A)','01','农业','000998','隆平高科'],last])])

    def test_duplicate_code_missing_context_or_partial_minor_pair_fail(self):
        for body in [[['农、林、牧、渔业(A)','01','农业','000998','隆平高科'],[None,None,None,'000998','重复']],
                     [[None,None,None,'000998','隆平高科']],
                     [['农、林、牧、渔业(A)','01',None,'000998','隆平高科']]]:
            with self.subTest(body=body),self.assertRaises(ValueError):self.parse([packet(1,body)])

    def test_bad_stock_identity_header_geometry_page_order_and_source_cannot_be_silently_fixed(self):
        base=packet(1,[['农、林、牧、渔业(A)','01','农业','000998','隆平高科']])
        for bad_code in ['998',998,'０００９９８']:
            changed=copy.deepcopy(base);changed['tables'][0]['rows'][1]['cells'][3]['literal']=bad_code
            with self.subTest(code=bad_code),self.assertRaises(ValueError):self.parse([changed])
        for change in [lambda p:p.update(physical_page=2),lambda p:p.update(source_sha256='d'*64),
                       lambda p:p['tables'][0]['rows'][0]['cells'][3].update(literal='公司简称'),
                       lambda p:p['tables'][0]['rows'][1]['cells'][3].update(bbox=[310,40,510,60])]:
            changed=copy.deepcopy(base);change(changed)
            with self.assertRaises(ValueError):self.parse([changed])
        with self.assertRaises(ValueError):self.parse([base,copy.deepcopy(base)])

    def test_unknown_cohort_member_is_preserved_and_2021_vintage_is_not_current_business(self):
        view=catalog.snapshot_catalog(bundle(),['SZ000998','SH600030','SH600001'],'2024-01-02T09:00:00+08:00',mode=catalog.ARCHIVE_RECONSTRUCTED)
        rows={r['instrument']:r for r in view['classifications']}
        self.assertEqual(len(rows),3)
        self.assertEqual(rows['SZ000998']['status'],'NONFINANCIAL_IN_SOURCE_VINTAGE')
        self.assertEqual(rows['SH600030']['status'],'FINANCIAL_IN_SOURCE_VINTAGE')
        self.assertEqual(rows['SH600001']['status'],'NOT_IN_SOURCE_VINTAGE')
        self.assertEqual(rows['SZ000998']['classification_period'],'2021Q3')
        self.assertFalse(view['current_business_identity_verified']);self.assertFalse(view['investment_factor_admitted'])

    def test_observed_and_archive_clock_boundaries_do_not_decode_hidden_payload(self):
        source=bundle();view=catalog.snapshot_catalog(source,['SZ000998'],'2024-01-02T09:00:00+08:00')
        self.assertEqual(view['classifications'][0]['status'],'NOT_AVAILABLE_AT_CLOCK')
        source['records']={'future':'must not be validated before visibility'}
        self.assertEqual(catalog.snapshot_catalog(source,['SZ000998'],'2024-01-02T09:00:00+08:00'),view)
        with self.assertRaises(ValueError):catalog.snapshot_catalog(source,['SZ000998'],OBSERVED)
        for clock in ['2021-12-27T20:06:26+00:00','2021-12-27T20:06:26.999999+00:00']:
            self.assertEqual(catalog.snapshot_catalog(bundle(),['SZ000998'],clock,mode=catalog.ARCHIVE_RECONSTRUCTED)['classifications'][0]['status'],'NOT_AVAILABLE_AT_CLOCK')
        self.assertEqual(catalog.snapshot_catalog(bundle(),['SZ000998'],PUBLIC,mode=catalog.ARCHIVE_RECONSTRUCTED)['classifications'][0]['status'],'NONFINANCIAL_IN_SOURCE_VINTAGE')

    def test_naive_clock_duplicate_cohort_and_visible_record_mutation_reject(self):
        for cohort,clock in [(['SZ000998'],'2024-01-02T09:00:00'),(['SZ000998','SZ000998'],PUBLIC)]:
            with self.assertRaises(ValueError):catalog.snapshot_catalog(bundle(),cohort,clock,mode=catalog.ARCHIVE_RECONSTRUCTED)
        source=bundle();source['records'][0]['sector_code']='J'
        with self.assertRaises(ValueError):catalog.snapshot_catalog(source,['SZ000998'],PUBLIC,mode=catalog.ARCHIVE_RECONSTRUCTED)


    def test_bounded_real_geometry_excerpts_match_reviewed_classification_literals(self):
        f=json.loads((Path(__file__).parent/'fixtures/industry-2021Q3-real-layout-excerpts.json').read_text())
        result=catalog.parse_catalog(f['records'],source_sha256=f['original_sha256'],public_by=PUBLIC,observed_at=OBSERVED,expected_pages=2)
        self.assertEqual({r['stock_code']:[r['sector_code'],r['industry_code'],r['industry_name']] for r in result['records']},f['expected'])
        self.assertFalse(f['CI_authenticates_original_PDF']);self.assertTrue(f['partial_rows_are_not_full_catalog'])


    def test_an_explicit_empty_cell_inside_the_page_is_not_merged_context(self):
        p=packet(1,[['农、林、牧、渔业(A)','01','农业','000998','隆平高科'],[None,None,None,'002041','登海种业']])
        p['tables'][0]['rows'][2]['cells'][0]['bbox']=[10,60,110,80]
        with self.assertRaisesRegex(ValueError,'ambiguous empty'):self.parse([p])

    def test_financial_sector_letter_and_literal_name_cannot_disagree(self):
        for label in ['金融业(A)','农业(J)']:
            with self.subTest(label=label),self.assertRaisesRegex(ValueError,'financial sector code/name'):
                self.parse([packet(1,[[label,'67','资本市场服务','600030','中信证券']])])


if __name__=='__main__':unittest.main()
