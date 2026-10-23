import copy
import unittest

from stock_rsi import annual_assets as assets
from stock_rsi import profitability_availability as legacy
try:
    from stock_rsi import asset_availability as source
except ImportError:
    source=None
from tests.test_industry_catalog import bundle
from tests.test_annual_profitability import pages
from tests.test_profitability_availability import document,case as legacy_case


def case(doc,status='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA'):
    year=doc['effective_fiscal_year']
    report=assets.make_report(doc['instrument'],year,doc['day'],doc['captured_at_utc'],
        doc['source_sha256'],doc['announcement_id'],assets.parse_balance_only(pages(year),year)) if status.startswith('ASSET_CELLS') else None
    return {'capture_key':doc['capture_key'],'instrument':doc['instrument'],'fiscal_year':year,
        'source_sha256':doc['source_sha256'],'status':status,'asset_report':report}


class AssetAvailabilityTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(source,'asset availability adapter missing')

    def snapshot(self,docs,cases,clock='2026-06-01T15:05:00+08:00',mode=assets.RECONSTRUCTED):
        return source.snapshot_availability(docs,cases.__getitem__,bundle(),['SZ000998','SH600030','SH600001'],clock,mode=mode)

    def test_default_observed_and_future_payload_are_never_read(self):
        d=document(2025,'2026-04-29','1')
        result=source.snapshot_availability([d],{}.__getitem__,bundle(),['SZ000998'],'2026-06-01T15:05:00+08:00')
        self.assertEqual(result['classifications'][0]['annual_status'],'NO_VISIBLE_ANNUAL_REPORT')
        old=document(2024,'2025-04-29','2')
        future={'day':'2026-06-02','captured_at_utc':'2026-10-23T00:00:00+00:00','payload':object()}
        self.assertEqual(self.snapshot([old],{'2':case(old)}),self.snapshot([old,future],{'2':case(old)}))

    def test_publication_day_end_and_exact_arrival_boundary(self):
        d=document(2025,'2026-04-29','1');d['captured_at_utc']='2026-04-30T00:00:00+00:00'
        before=self.snapshot([d],{},clock='2026-04-29T23:59:59.999998+08:00')
        self.assertEqual(before['classifications'][-1]['annual_status'],'NO_VISIBLE_ANNUAL_REPORT')
        at=self.snapshot([d],{'1':case(d)},clock='2026-04-29T23:59:59.999999+08:00')
        self.assertEqual(at['classifications'][-1]['latest_fiscal_year'],2025)
        before=self.snapshot([d],{},clock='2026-04-30T07:59:59.999999+08:00',mode=assets.OBSERVED)
        self.assertEqual(before['classifications'][-1]['annual_status'],'NO_VISIBLE_ANNUAL_REPORT')
        at=self.snapshot([d],{'1':case(d)},clock='2026-04-30T08:00:00+08:00',mode=assets.OBSERVED)
        self.assertEqual(at['classifications'][-1]['selected_capture_key'],'1')

    def test_newest_failed_case_blocks_older_and_current_only_stays_current_only(self):
        old,new=document(2024,'2025-04-29','1'),document(2025,'2026-04-29','2')
        for status in ('ASSET_SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED','SOURCE_PDF_EXTRACTION_UNSUPPORTED'):
            row=self.snapshot([old,new],{'2':case(new,status)})['classifications'][-1]
            self.assertEqual(row['selected_capture_key'],'2');self.assertEqual(row['annual_status'],'LATEST_'+status)
            self.assertNotIn('asset_record_id',row)
        c=case(new);r=c['asset_report'];r['payload']['balances'].pop('2024-12-31')
        from stock_rsi.data import digest
        r['record_id']=digest({k:v for k,v in r.items() if k!='record_id'})
        row=self.snapshot([new],{'2':c})['classifications'][-1]
        self.assertEqual(row['balance_periods'],['2025-12-31']);self.assertFalse(row['has_explicit_prior_year_end'])
        self.assertNotIn('asset_report',row);self.assertNotIn('value_CNY',str(row))

    def test_fiscal_order_same_day_ambiguity_and_identical_byte_witness(self):
        new,old=document(2025,'2026-04-29','10'),document(2024,'2026-05-29','3')
        self.assertEqual(self.snapshot([new,old],{'10':case(new)})['classifications'][-1]['selected_capture_key'],'10')
        other=document(2025,'2026-04-29','2','b'*64)
        self.assertEqual(self.snapshot([new,other],{})['classifications'][-1]['annual_status'],'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS')
        other['source_sha256']=new['source_sha256']
        row=self.snapshot([new,other],{'2':case(other)})['classifications'][-1]
        self.assertEqual(row['selected_capture_key'],'2');self.assertEqual(row['selected_edition_capture_keys'],['2','10'])

    def test_pre2026_selection_matches_unchanged_legacy_and_future_editions_do_not_change_it(self):
        a,b=document(2022,'2023-04-29','1'),document(2023,'2024-04-29','2')
        future=document(2025,'2026-04-29','3')
        clock='2024-06-01T09:00:00+08:00';cohort=['SZ000998','SH600030','SH600001']
        old=legacy.snapshot_availability([a,b],{'2':legacy_case(b)}.__getitem__,bundle(),cohort,clock,mode=assets.RECONSTRUCTED)
        new=self.snapshot([a,b,future],{'2':case(b)},clock=clock)
        for left,right in zip(old['classifications'],new['classifications']):
            for k in ('instrument','industry_status','latest_fiscal_year','latest_publication_day',
                'selected_edition_capture_keys','selected_capture_key','selected_source_sha256'):
                self.assertEqual(left.get(k),right.get(k))
        with self.assertRaises(ValueError):legacy.snapshot_availability([],{}.__getitem__,bundle(),cohort,'2026-01-01T09:00:00+08:00')

    def test_selected_source_corruption_unknown_state_and_after_cutoff_fail_closed(self):
        d=document(2025,'2026-04-29','1')
        for mutate in (lambda c:c.update(source_sha256='b'*64),lambda c:c.update(status='GUESS'),
            lambda c:c['asset_report'].update(observed_at='2026-10-21T00:00:00+00:00'),
            lambda c:c['asset_report']['payload'].update(announcement_id='9')):
            c=case(d);mutate(c)
            with self.assertRaises(ValueError):self.snapshot([d],{'1':c})
        for clock in ('2026-10-21T15:05:00.000001+08:00','2027-01-01T09:00:00+08:00','2026-01-01'):
            with self.assertRaises(ValueError):self.snapshot([],{},clock=clock)
        self.assertEqual(len(self.snapshot([],{},clock='2026-10-21T15:05:00+08:00')['classifications']),3)


if __name__=='__main__':unittest.main()
