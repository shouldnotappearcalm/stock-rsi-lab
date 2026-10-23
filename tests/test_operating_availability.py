import copy
import unittest

from stock_rsi import annual_operating as op
try:
    from stock_rsi import operating_availability as availability
except ImportError:
    availability = None
from tests.test_annual_operating import source
from tests.test_industry_catalog import bundle
from tests.test_profitability_availability import document


def case(doc, status='OPERATING_CELLS_SUPPORTED_PENDING_SOURCE_QA'):
    year=doc['effective_fiscal_year']
    report=op.make_report(doc['instrument'],year,doc['day'],doc['captured_at_utc'],doc['source_sha256'],
        doc['announcement_id'],op.parse_report(source(year),year)) if status.startswith('OPERATING_CELLS') else None
    return {'capture_key':doc['capture_key'],'instrument':doc['instrument'],'fiscal_year':year,
            'source_sha256':doc['source_sha256'],'status':status,'operating_report':report}


class OperatingAvailabilityTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(availability,'operating availability module missing')

    def snapshot(self, docs, cases, clock='2024-06-01T15:05:00+08:00', mode=op.RECONSTRUCTED):
        return availability.snapshot_availability(docs,cases.__getitem__,bundle(),
            ['SZ000998','SH600030','SH600001'],clock,mode=mode)

    def test_default_observed_and_future_metadata_payload_are_not_read(self):
        old=document(2022,'2023-04-29','1')
        result=availability.snapshot_availability([old],{}.__getitem__,bundle(),['SZ000998'],'2024-06-01T15:05:00+08:00')
        self.assertEqual(result['classifications'][0]['annual_status'],'NO_VISIBLE_ANNUAL_REPORT')
        future={'day':'2025-04-29','captured_at_utc':'2026-10-22T00:00:00+00:00','unread_payload':object()}
        self.assertEqual(self.snapshot([old],{'1':case(old)}),self.snapshot([old,future],{'1':case(old)}))

    def test_publication_day_end_and_actual_arrival_boundaries(self):
        doc=document(2023,'2024-04-29','1');doc['captured_at_utc']='2024-04-30T00:00:00+00:00'
        self.assertEqual(self.snapshot([doc],{},'2024-04-29T23:59:59.999998+08:00')['classifications'][-1]['annual_status'],'NO_VISIBLE_ANNUAL_REPORT')
        self.assertEqual(self.snapshot([doc],{'1':case(doc)},'2024-04-29T23:59:59.999999+08:00')['classifications'][-1]['selected_capture_key'],'1')
        self.assertEqual(self.snapshot([doc],{},'2024-04-30T07:59:59.999999+08:00',op.OBSERVED)['classifications'][-1]['annual_status'],'NO_VISIBLE_ANNUAL_REPORT')
        self.assertEqual(self.snapshot([doc],{'1':case(doc)},'2024-04-30T08:00:00+08:00',op.OBSERVED)['classifications'][-1]['selected_capture_key'],'1')

    def test_newer_failed_report_blocks_supported_old_report(self):
        old,new=document(2022,'2023-04-29','1'),document(2023,'2024-04-29','2')
        for status in availability.FAILURES:
            row=self.snapshot([old,new],{'2':case(new,status)})['classifications'][-1]
            self.assertEqual(row['annual_status'],'LATEST_'+status)
            self.assertEqual(row['selected_capture_key'],'2')
            self.assertNotIn('operating_record_id',row)

    def test_late_old_fiscal_reissue_does_not_replace_newer_fiscal_year(self):
        new,old=document(2023,'2024-04-29','1'),document(2017,'2024-05-29','2')
        self.assertEqual(self.snapshot([new,old],{'1':case(new)})['classifications'][-1]['selected_capture_key'],'1')

    def test_same_day_conflict_and_identical_PDF_witness_keep_all_editions(self):
        a,b=document(2023,'2024-04-29','10'),document(2023,'2024-04-29','2','b'*64)
        self.assertEqual(self.snapshot([a,b],{})['classifications'][-1]['annual_status'],'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS')
        b['source_sha256']=a['source_sha256']
        row=self.snapshot([a,b],{'2':case(b)})['classifications'][-1]
        self.assertEqual(row['selected_capture_key'],'2');self.assertEqual(row['selected_edition_capture_keys'],['2','10'])

    def test_full_cohort_keeps_financial_unknown_rows_and_exposes_no_amounts_or_ratios(self):
        doc=document(2023,'2024-04-29','1');result=self.snapshot([doc],{'1':case(doc)})
        self.assertEqual(len(result['classifications']),3)
        self.assertEqual([r['industry_status'] for r in result['classifications']],
            ['NOT_IN_SOURCE_VINTAGE','FINANCIAL_IN_SOURCE_VINTAGE','NONFINANCIAL_IN_SOURCE_VINTAGE'])
        self.assertTrue(result['source_only_no_monetary_values_exposed'])
        self.assertNotIn('value_CNY',str(result));self.assertNotIn('operating_profit_to_lagged_assets',str(result))
        self.assertFalse(result['investment_factor_admitted'])

    def test_selected_case_record_source_and_clock_corruption_fail_closed(self):
        doc=document(2023,'2024-04-29','1')
        for change in (lambda c:c.update(source_sha256='b'*64),lambda c:c.update(status='UNKNOWN'),
            lambda c:c['operating_report'].update(observed_at='2026-10-21T00:00:00+00:00'),
            lambda c:c['operating_report']['payload'].update(announcement_id='99'),
            lambda c:c['operating_report']['payload']['parsed']['income']['2023-12-31']['revenue'].update(value_CNY='99.00')):
            current=case(doc);change(current)
            with self.subTest(change=change),self.assertRaises(ValueError):self.snapshot([doc],{'1':current})
        current=case(doc);current['status']=availability.FAILURES[0]
        with self.assertRaises(ValueError):self.snapshot([doc],{'1':current})

    def test_cutoff_naive_clock_unknown_mode_and_duplicate_cohort_fail(self):
        for clock in ('2026-01-01T00:00:00+08:00','2024-01-01'):
            with self.assertRaises(ValueError):self.snapshot([],{},clock)
        with self.assertRaises(ValueError):self.snapshot([],{},mode='UNKNOWN')
        with self.assertRaises(ValueError):availability.snapshot_availability([],{}.__getitem__,bundle(),['SZ000998']*2,'2024-01-01T00:00:00+08:00')


if __name__=='__main__':unittest.main()
