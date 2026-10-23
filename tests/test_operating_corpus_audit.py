import copy
import unittest

try:
    from scripts import audit_operating_corpus_source as audit
except ImportError:
    audit=None
from stock_rsi import annual_operating as op
from stock_rsi import operating_availability as availability
from stock_rsi.data import digest
from tests.test_annual_operating import source
from tests.test_industry_catalog import bundle
from tests.test_profitability_availability import document
from tests.test_operating_availability import case


class OperatingCorpusAuditTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(audit,'independent operating corpus checker missing')

    def source_case(self):
        doc=document(2023,'2024-04-29','1');pages=source(admin='-5.00')
        report=op.make_report(doc['instrument'],2023,doc['day'],doc['captured_at_utc'],doc['source_sha256'],doc['announcement_id'],op.parse_report(pages,2023))
        result={'capture_key':'1','instrument':doc['instrument'],'fiscal_year':2023,'source_sha256':doc['source_sha256'],
            'status':availability.SUPPORTED,'operating_report':report}
        return pages,doc,result

    def test_all_twelve_original_signed_cells_are_checked_without_source_ratio(self):
        pages,doc,current=self.source_case();self.assertEqual(audit.check_case(pages,doc,current),12)
        self.assertEqual(current['operating_report']['payload']['parsed']['income']['2023-12-31']['administrative_expenses']['value_CNY'],'-5.00')

    def test_forged_amount_unit_column_and_parent_scope_fail_independent_source_check(self):
        pages,doc,baseline=self.source_case()
        for field,value in [('value_CNY','500.00'),('unit','万元'),('column_index',1),('statement','母公司利润表')]:
            current=copy.deepcopy(baseline);current['operating_report']['payload']['parsed']['income']['2023-12-31']['administrative_expenses'][field]=value
            report=current['operating_report'];report['record_id']=digest({k:v for k,v in report.items() if k!='record_id'})
            with self.subTest(field=field),self.assertRaises(ValueError):audit.check_case(pages,doc,current)
        parent=copy.deepcopy(baseline);cell=parent['operating_report']['payload']['parsed']['income']['2023-12-31']['administrative_expenses']
        cell['page']=4
        report=parent['operating_report'];report['record_id']=digest({k:v for k,v in report.items() if k!='record_id'})
        with self.assertRaises(ValueError):audit.check_case(pages,doc,parent)

    def test_edited_original_page_and_consolidated_header_cannot_be_hidden_by_payload(self):
        pages,doc,current=self.source_case();bad=copy.deepcopy(pages);bad[2]=bad[2].replace('管理费用 七、64 -5.00 2.00','管理费用 七、64 -50.00 2.00')
        with self.assertRaises(ValueError):audit.check_case(bad,doc,current)
        bad=copy.deepcopy(pages);bad[2]=bad[2].replace('合并利润表','母公司利润表')
        with self.assertRaises(ValueError):audit.check_case(bad,doc,current)

    def test_original_split_numbered_statement_title_is_counted_once(self):
        for title in ('1、\n合并资产负债表','1\n、合并资产负债表'):
            pages,doc,current=self.source_case();pages[0]=pages[0].replace('合并资产负债表',title)
            try:count=audit.check_case(pages,doc,current)
            except ValueError as error:self.fail('legitimate split original title rejected: '+str(error))
            self.assertEqual(count,12)

    def test_latest_failed_source_selection_is_reconstructed_and_forgery_rejected(self):
        old,new=document(2022,'2023-04-29','1'),document(2023,'2024-04-29','2');cohort=['SZ000998']
        cases={'1':case(old),'2':case(new,'OPERATING_SOURCE_SCHEMA_UNSUPPORTED')};clock='2024-06-01T15:05:00+08:00'
        view=availability.snapshot_availability([old,new],cases.__getitem__,bundle(),cohort,clock,mode=op.RECONSTRUCTED)
        self.assertEqual(audit.check_selection([old,new],cases,view,cohort,clock,op.RECONSTRUCTED),1)
        bad=copy.deepcopy(view);bad['classifications'][0]['selected_capture_key']='1'
        with self.assertRaises(ValueError):audit.check_selection([old,new],cases,bad,cohort,clock,op.RECONSTRUCTED)
        observed=availability.snapshot_availability([old,new],{}.__getitem__,bundle(),cohort,clock)
        self.assertEqual(audit.check_selection([old,new],{},observed,cohort,clock,op.OBSERVED),1)


if __name__=='__main__':unittest.main()
