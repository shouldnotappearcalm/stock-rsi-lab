import copy
import unittest
from decimal import Decimal as D
from stock_rsi.calendar import TradingCalendar
try:
    from stock_rsi.distribution_event_compiler import compile_distribution_events
except ImportError:
    compile_distribution_events=None


class DistributionEventCompilerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(compile_distribution_events)
        self.calendar=TradingCalendar(['2024-06-25','2024-06-26','2024-06-27','2024-06-28'])
        self.row={'code':'sh.603826','dividPlanDate':'2024-06-21','dividRegistDate':'2024-06-26',
            'dividOperateDate':'2024-06-27','dividPayDate':'2024-06-27','dividStockMarketDate':'2024-06-27',
            'dividCashPsBeforeTax':'0.1','dividStocksPs':'0.4','dividReserveToStockPs':'',
            'dividCashStock':'10送4派1元（含税）'}
        self.packets={'SH603826':{'instrument':'SH603826','distributions':[self.row]}}
        self.document={'instrument':'SH603826','day':'2024-06-21','file':'notice.pdf','sha256':'a'*64}
        self.proof={'documents':[self.document],'cash_overrides':{},'capital_tax':{},
            'stock_dividend_tax_bases':{'SH603826|2024-06-27':{'verified':True,
                'expected_stock_per_original_share':'0.4','taxable_income_per_original_share':'0.4',
                'source_file':'notice.pdf','source_sha256':'a'*64}},'supplementary_distributions':[]}

    def compile(self):return compile_distribution_events(self.packets,self.proof,self.calendar)

    def test_stock_dividend_keeps_taxable_income_and_primary_binding_without_mutating_source(self):
        before=copy.deepcopy((self.packets,self.proof));events,receipts=self.compile()
        self.assertEqual((self.packets,self.proof),before)
        self.assertEqual(len(events),1);e=events[0]
        self.assertEqual((e.cash_per_share,e.stock_per_share,e.capital_per_share),(D('.1'),D('.4'),D(0)))
        self.assertEqual(e.stock_taxable_income_per_share,D('.4'));self.assertTrue(e.stock_tax_basis_verified)
        self.assertFalse(e.capital_tax_exempt_verified)
        self.assertEqual(receipts[0]['source_kind'],'VENDOR_DISTRIBUTION')
        self.assertEqual(receipts[0]['primary_source_sha256'],['a'*64])
        self.assertEqual(e.event_id,self.compile()[0][0].event_id)

    def test_unverified_capital_is_retained_and_needs_actual_zero_entitlement_or_primary_proof(self):
        self.row.update(dividStocksPs='0',dividReserveToStockPs='0.4',dividCashStock='10转4派1元')
        self.proof['stock_dividend_tax_bases']={}
        events,receipts=self.compile()
        self.assertEqual(events[0].capital_per_share,D('.4'));self.assertFalse(events[0].capital_tax_exempt_verified)
        self.assertTrue(receipts[0]['requires_zero_record_ownership_if_tax_unverified'])
        self.proof['capital_tax']={'SH603826|2024-06-27':{'verified_exempt':True,
            'source_file':'notice.pdf','source_sha256':'a'*64}}
        events,receipts=self.compile();self.assertTrue(events[0].capital_tax_exempt_verified)
        self.assertFalse(receipts[0]['requires_zero_record_ownership_if_tax_unverified'])

    def test_explicit_cash_only_blank_capital_and_primary_cash_supplement_preserve_both_origins(self):
        self.row.update(dividStocksPs='0',dividCashStock='10派1元（含税）',dividStockMarketDate='')
        self.proof['stock_dividend_tax_bases']={}
        supplement=copy.deepcopy(self.row);supplement.update(dividOperateDate='2024-06-28',dividRegistDate='2024-06-27',
            dividPayDate='2024-06-28',dividCashPsBeforeTax='0.12',dividReserveToStockPs='0',dividCashStock='PRIMARY_CASH_ONLY_NOTICE')
        self.proof['supplementary_distributions']=[{'instrument':'SH603826','record':supplement,
            'source_file':'notice.pdf','source_sha256':'a'*64}]
        events,receipts=self.compile()
        self.assertEqual(len(events),2);self.assertEqual(events[1].cash_per_share,D('.12'))
        self.assertEqual([r['source_kind'] for r in receipts],['VENDOR_DISTRIBUTION','PRIMARY_NOTICE_SUPPLEMENT'])
        self.assertEqual(len(self.packets['SH603826']['distributions']),1)

    def test_missing_unknown_components_or_changed_primary_binding_fail_closed(self):
        original=copy.deepcopy((self.packets,self.proof))
        def bad_cash():self.row['dividCashPsBeforeTax']=''
        def bad_capital():self.row['dividCashStock']='unknown'
        def bad_code():self.row['code']='sz.603826'
        def bad_sha():self.proof['stock_dividend_tax_bases']['SH603826|2024-06-27']['source_sha256']='b'*64
        def bad_ratio():self.row['dividStocksPs']='.5'
        def bad_doc_date():self.document['day']='2024-06-22'
        for mutate in (bad_cash,bad_capital,bad_code,bad_sha,bad_ratio,bad_doc_date):
            self.packets,self.proof=copy.deepcopy(original);self.row=self.packets['SH603826']['distributions'][0];self.document=self.proof['documents'][0]
            mutate()
            with self.assertRaises(ValueError):self.compile()

    def test_duplicate_or_orphan_proofs_and_out_of_session_events_are_rejected(self):
        original=copy.deepcopy((self.packets,self.proof))
        self.packets['SH603826']['distributions'].append(copy.deepcopy(self.row))
        with self.assertRaises(ValueError):self.compile()
        self.packets,self.proof=copy.deepcopy(original)
        self.proof['capital_tax']['SH603826|2024-06-28']={'verified_exempt':True,'source_file':'notice.pdf','source_sha256':'a'*64}
        with self.assertRaises(ValueError):self.compile()
        self.packets,self.proof=copy.deepcopy(original)
        self.packets['SH603826']['distributions'][0]['dividRegistDate']='2024-06-23'
        with self.assertRaises(ValueError):self.compile()
