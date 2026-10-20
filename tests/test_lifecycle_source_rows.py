import copy
import unittest
from datetime import date
try:
    from stock_rsi.lifecycle_source_rows import source_rows_on
except ImportError:source_rows_on=None


class LifecycleSourceRowsTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(source_rows_on)

    def proof(self,kind,day):
        return {'kind':kind,'effective_date':day,'verified_primary_boundary':True,'primary_document_sha256':'a'*64}

    def test_missing_listing_prefix_is_audited_only_when_no_price_or_inventory_is_required(self):
        bars={'A':{'2024-03-01':{'date':'2024-03-01','close':'10'}}};before=copy.deepcopy(bars)
        p={'A':self.proof('LISTING_BEGIN','2024-03-01')}
        rows,missing=source_rows_on(bars,date(2024,2,29),set(),p)
        self.assertEqual(rows,{});self.assertEqual(missing[0]['reason'],'BEFORE_PRIMARY_LISTING_BOUNDARY')
        self.assertEqual(bars,before)
        with self.assertRaises(ValueError):source_rows_on(bars,date(2024,2,29),{'A'},p)
        with self.assertRaises(ValueError):source_rows_on(bars,date(2024,2,29),(x for x in ['A']),p)
        self.assertEqual(source_rows_on(bars,date(2024,3,1),{'A'},p)[0],{'A':bars['A']['2024-03-01']})
        with self.assertRaises(ValueError):source_rows_on(bars,date(2024,3,4),set(),p)

    def test_delisting_requires_flat_inventory_and_no_pending_orders_even_if_vendor_row_exists(self):
        bars={'A':{'2024-08-30':{'date':'2024-08-30','tradestatus':'0','close':'0.4'}}}
        p={'A':self.proof('DELISTING_END','2024-08-30')}
        with self.assertRaises(ValueError):source_rows_on(bars,date(2024,8,30),{'A'},p)
        rows,missing=source_rows_on(bars,date(2024,8,30),set(),p)
        self.assertEqual(rows,{});self.assertTrue(missing[0]['original_row_present'])
        self.assertEqual(source_rows_on(bars,date(2024,9,2),set(),p)[0],{})
        with self.assertRaises(ValueError):source_rows_on(bars,date(2024,9,2),{'A'},p)

    def test_unexplained_gap_wrong_date_unknown_security_and_unverified_proof_fail(self):
        p={'A':self.proof('LISTING_BEGIN','2024-03-01')}
        with self.assertRaises(ValueError):source_rows_on({'A':{}},date(2024,2,29),set(),{})
        for override in ({'verified_primary_boundary':False},{'primary_document_sha256':''},{'effective_date':'2024-02-30'}):
            bad={'A':{**p['A'],**override}}
            with self.assertRaises(ValueError):source_rows_on({'A':{}},date(2024,2,29),set(),bad)
        with self.assertRaises(ValueError):source_rows_on({'A':{'2024-03-01':{'date':'2024-03-02'}}},date(2024,3,1),set(),p)
        with self.assertRaises(ValueError):source_rows_on({'A':{}},date(2024,2,29),{'B'},p)
