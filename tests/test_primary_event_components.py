"""Synthetic evaluator completion only; no market data, PDF fetch or replay."""
import copy
import importlib
import unittest
from datetime import date
from decimal import Decimal as D, ROUND_HALF_UP
from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2
from stock_rsi.stock_distribution_account import StockDistributionAccount


class PrimaryEventComponentsTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('stock_rsi.primary_event_components')
        except ModuleNotFoundError:self.fail('primary event components adapter missing')

    def fixture(self,stock=False):
        code='SH600001';key=code+'|2024-06-14'
        row={'code':'sh.600001','dividPlanDate':'2024-06-07','dividRegistDate':'2024-06-13',
             'dividOperateDate':'2024-06-14','dividPayDate':'2024-06-14','dividStockMarketDate':'',
             'dividCashPsBeforeTax':'0.286','dividCashPsAfterTax':'0.2574','dividStocksPs':'0',
             'dividReserveToStockPs':'','dividCashStock':'10派2.86元'}
        rows=[row,dict(row,dividCashPsBeforeTax='0.091',dividCashPsAfterTax='0.0819',dividCashStock='10派0.91元')]
        if stock:
            row.update(dividStocksPs='0.4',dividStockMarketDate='2024-06-14',dividCashStock='10送4派2.86元');rows=[row]
        packets={code:{'instrument':code,'distributions':rows,'unrelated_original_metadata':['retained']}}
        proof={'verified':True,'version':1,'kind':'PRIMARY_STOCK_ZERO_CAPITAL' if stock else 'PRIMARY_TWO_CASH_COMPONENT_SUM',
               'instrument':code,'publication_day':'2024-06-07','record_date':'2024-06-13','ex_date':'2024-06-14',
               'cash_payment_date':'2024-06-14','stock_listing_date':'2024-06-14' if stock else None,
               'source_file':'notice.pdf','source_sha256':'a'*64,'primary_pages':[1,2],
               'stock_per_original_share':'0.4' if stock else '0','capital_per_original_share':'0'}
        if stock:proof.update(source_row_sha256=digest(row),cash_per_original_share='0.286')
        else:proof.update(components=[{'source_row_sha256':digest(r),'cash_per_original_share':r['dividCashPsBeforeTax']} for r in rows],combined_cash_per_original_share='0.377')
        proofs={'documents':[{'file':'notice.pdf','sha256':'a'*64,'instrument':code,'day':'2024-06-07'}],
                'capital_tax':{},'stock_dividend_tax_bases':{},'supplementary_distributions':[],
                'primary_event_component_contract':'PRIMARY_EVENT_COMPONENT_COMPLETION_V1',
                'primary_event_components':{key:proof}}
        cal=TradingCalendar(['2024-06-12','2024-06-13','2024-06-14','2024-06-17'])
        return packets,proofs,cal,key

    def test_two_component_exact_cash_sum_immutability_and_derived_identity(self):
        m=self.api();p,f,c,key=self.fixture();before=copy.deepcopy((p,f))
        projected,pr=m.project_primary_event_components(p,f);self.assertEqual((p,f),before)
        self.assertIsNot(projected,p);self.assertEqual(len(projected['SH600001']['distributions']),1)
        self.assertEqual(projected['SH600001']['distributions'][0]['dividCashPsBeforeTax'],'0.377')
        events,receipts=m.compile_primary_event_components(p,f,c)
        self.assertEqual(len(events),1);self.assertEqual(events[0].cash_per_share,D('0.377'))
        r=receipts[0];self.assertEqual(r['source_kind'],'PRIMARY_TWO_CASH_COMPONENT_SUM')
        self.assertEqual(r['original_source_row_sha256'],[digest(x) for x in p['SH600001']['distributions']])
        self.assertEqual(r['derived_source_row_sha256'],digest(projected['SH600001']['distributions'][0]))
        self.assertEqual(r['projection_receipt_sha256'],digest(pr[0]));self.assertEqual(r['primary_source_sha256'],['a'*64])
        original_derived_event=compile_distribution_events_v2(projected,{**f,'primary_event_components':{}},c)[0][0]
        self.assertNotEqual(events[0].event_id,original_derived_event.event_id)
        self.assertEqual((events,receipts),m.compile_primary_event_components(p,f,c));self.assertEqual((p,f),before)

    def test_single_combined_event_rounding_is_not_separate_component_cent_rounding(self):
        m=self.api();p,f,c,key=self.fixture()
        events,receipts=m.compile_primary_event_components(p,f,c)
        note=receipts[0]['projection_receipt']
        self.assertEqual(note['cash_settlement_contract'],'ONE_COMBINED_PER_REGISTERED_SHARE_EVENT_ACCOUNT_EXISTING_AGGREGATE_ROUNDING')
        self.assertFalse(note['separate_component_cent_settlement_equivalence_certified'])
        account=StockDistributionAccount(c,'100',events,tax_reserve_rate='0')
        account.broker.positions={'SH600001':[{'quantity':4,'price':D('1'),'bought_on':date(2024,6,12)}]}
        account.end_day(date(2024,6,13));account.start_day(date(2024,6,14))
        self.assertEqual(account.cash_claims[0]['gross'],D('1.51'))
        separately=sum((D(x)*4).quantize(D('.01'),rounding=ROUND_HALF_UP) for x in ('0.286','0.091'))
        self.assertEqual(separately,D('1.50'));self.assertNotEqual(account.cash_claims[0]['gross'],separately)

    def test_reference_cash_component_tampering_omitted_repeated_or_orphan_rejected(self):
        m=self.api();original=self.fixture()
        for change in ('reference','one_cash','component_hash','repeated_component','missing_component','third_component','orphan','repeated_source'):
            p,f,c,key=copy.deepcopy(original);proof=f['primary_event_components'][key]
            if change=='reference':proof['combined_cash_per_original_share']='0.37444'
            if change=='one_cash':proof['components'][0]['cash_per_original_share']='0.285'
            if change=='component_hash':proof['components'][0]['source_row_sha256']='b'*64
            if change=='repeated_component':proof['components'][1]=copy.deepcopy(proof['components'][0])
            if change=='missing_component':proof['components'].pop()
            if change=='third_component':proof['components'].append(copy.deepcopy(proof['components'][0]))
            if change=='orphan':f['primary_event_components']['SH600001|2024-06-17']=copy.deepcopy(proof)
            if change=='repeated_source':p['SH600001']['distributions'][1]=copy.deepcopy(p['SH600001']['distributions'][0])
            before=copy.deepcopy((p,f))
            with self.subTest(change=change),self.assertRaises(ValueError):m.compile_primary_event_components(p,f,c)
            self.assertEqual((p,f),before)

    def test_cash_times_noncash_and_primary_identity_fail_closed(self):
        m=self.api();original=self.fixture()
        for change in ('record','pay','pub','issuer','stock','capital','listed','doc_missing','docsha','docissuer','docday','pagezero','pagebool','wrongkind','wrongversion'):
            p,f,c,key=copy.deepcopy(original);proof=f['primary_event_components'][key];row=p['SH600001']['distributions'][1]
            if change in ('record','pay','pub'):row[{'record':'dividRegistDate','pay':'dividPayDate','pub':'dividPlanDate'}[change]]='2024-06-12';proof['components'][1]['source_row_sha256']=digest(row)
            if change=='issuer':proof['instrument']='SH600002'
            if change=='stock':row['dividStocksPs']='0.1';proof['components'][1]['source_row_sha256']=digest(row)
            if change=='capital':row['dividReserveToStockPs']='0.2';proof['components'][1]['source_row_sha256']=digest(row)
            if change=='listed':row['dividStockMarketDate']='2024-06-14';proof['components'][1]['source_row_sha256']=digest(row)
            if change=='doc_missing':f['documents']=[]
            if change=='docsha':f['documents'][0]['sha256']='b'*64
            if change=='docissuer':f['documents'][0]['instrument']='SH600002'
            if change=='docday':f['documents'][0]['day']='2024-06-08'
            if change=='pagezero':proof['primary_pages']=[0]
            if change=='pagebool':proof['primary_pages']=[True]
            if change=='wrongkind':proof['kind']='GENERAL_OVERRIDE'
            if change=='wrongversion':proof['version']=True
            with self.subTest(change=change),self.assertRaises(ValueError):m.compile_primary_event_components(p,f,c)

    def test_stock_blank_only_becomes_zero_tax_remains_unknown_and_owned_account_rejects(self):
        m=self.api();p,f,c,key=self.fixture(stock=True);before=copy.deepcopy(p)
        with self.assertRaises(ValueError):compile_distribution_events_v2(p,f,c)
        projected,pr=m.project_primary_event_components(p,f)
        expected=copy.deepcopy(p);expected['SH600001']['distributions'][0]['dividReserveToStockPs']='0'
        self.assertEqual(projected,expected);self.assertEqual(p,before)
        events,receipts=m.compile_primary_event_components(p,f,c);e=events[0]
        self.assertEqual(e.stock_per_share,D('.4'));self.assertEqual(e.capital_per_share,0)
        self.assertFalse(e.stock_tax_basis_verified);self.assertFalse(e.capital_tax_exempt_verified)
        self.assertEqual(e.stock_taxable_income_per_share,0);self.assertTrue(receipts[0]['requires_zero_record_ownership_if_tax_unverified'])
        account=StockDistributionAccount(c,'100',events,tax_reserve_rate='.2')
        account.broker.positions={'SH600001':[{'quantity':100,'price':D('1'),'bought_on':date(2024,6,12)}]}
        account.end_day(date(2024,6,13));state=copy.deepcopy((account.broker.cash,account.broker.positions,account.cash_claims,account.stock_claims))
        with self.assertRaisesRegex(ValueError,'stock dividend tax basis'):account.start_day(date(2024,6,14))
        self.assertEqual((account.broker.cash,account.broker.positions,account.cash_claims,account.stock_claims),state)

    def test_zero_completion_cannot_override_nonblank_cash_stock_tax_or_other_contracts(self):
        m=self.api();original=self.fixture(stock=True)
        for change in ('nonblank','cash','stock','tax','capital_tax','cash_override','precision','supplement','extra_tax_flag'):
            p,f,c,key=copy.deepcopy(original);proof=f['primary_event_components'][key]
            if change=='nonblank':p['SH600001']['distributions'][0]['dividReserveToStockPs']='0';proof['source_row_sha256']=digest(p['SH600001']['distributions'][0])
            if change=='cash':proof['cash_per_original_share']='0.285'
            if change=='stock':proof['stock_per_original_share']='0.5'
            if change in ('tax','capital_tax','cash_override','precision'):f[{'tax':'stock_dividend_tax_bases','capital_tax':'capital_tax','cash_override':'cash_overrides','precision':'component_precision_overrides'}[change]]={key:{'verified':True}}
            if change=='supplement':f['supplementary_distributions']=[{'instrument':'SH600001','record':copy.deepcopy(p['SH600001']['distributions'][0])}]
            if change=='extra_tax_flag':proof['stock_tax_basis_verified']=True
            with self.subTest(change=change),self.assertRaises(ValueError):m.compile_primary_event_components(p,f,c)

    def test_v3_only_precision_contract_is_rejected_globally_before_empty_completion_return(self):
        m=self.api()
        for completion in (True,False):
            for overrides in ({'SZ000002|2024-06-14':{'verified':True}}, [], None, False, 'unsupported'):
                p,f,c,key=self.fixture()
                if not completion:
                    p['SH600001']['distributions']=p['SH600001']['distributions'][:1]
                    f['primary_event_components']={}
                f['component_precision_overrides']=overrides
                before=copy.deepcopy((p,f))
                with self.subTest(completion=completion,overrides=overrides):
                    with self.assertRaises(ValueError):m.project_primary_event_components(p,f)
                    with self.assertRaises(ValueError):m.compile_primary_event_components(p,f,c)
                self.assertEqual((p,f),before)
        p,f,c,key=self.fixture();f['component_precision_overrides']={}
        self.assertEqual(m.compile_primary_event_components(p,f,c),m.compile_primary_event_components(p,{k:v for k,v in f.items() if k!='component_precision_overrides'},c))

    def test_untouched_events_and_v2_cash_precision_are_exactly_preserved(self):
        m=self.api();p,f,c,key=self.fixture()
        untouched=copy.deepcopy(p['SH600001']['distributions'][0]);untouched.update(code='sz.001914',dividCashPsBeforeTax='0.240097')
        p['SZ001914']={'instrument':'SZ001914','distributions':[untouched]}
        f['documents'].append({'file':'precision.pdf','sha256':'c'*64,'instrument':'SZ001914','day':'2024-06-07'})
        f['cash_override_contract']='PRIMARY_NOTICE_CASH_PRECISION_V1';f['cash_overrides']={'SZ001914|2024-06-14':{'verified':True,'kind':'PRIMARY_NOTICE_CASH_PRECISION','source_row_sha256':digest(untouched),'expected_vendor_cash_per_share':'0.240097','effective_cash_per_share':'0.2400974','source_file':'precision.pdf','source_sha256':'c'*64}}
        legacy=compile_distribution_events_v2({'SZ001914':p['SZ001914']},{**f,'primary_event_components':{}},c)
        events,receipts=m.compile_primary_event_components(p,f,c)
        self.assertEqual(events[1:],legacy[0]);self.assertEqual(receipts[1:],legacy[1])
        only={'SZ001914':p['SZ001914']};empty={**f,'primary_event_components':{}}
        self.assertEqual(m.compile_primary_event_components(only,empty,c),compile_distribution_events_v2(only,empty,c))

if __name__=='__main__':unittest.main()
