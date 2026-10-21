import copy
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from stock_rsi.calendar import TradingCalendar
from stock_rsi.stock_distribution_account import StockDistributionAccount


class ExtensionEventTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('scripts.prepare_low_beta60_extension_events')
        except ModuleNotFoundError:self.fail('append-only extension source compilation is absent')

    def inputs(self):
        f=json.loads((Path(__file__).parent/'fixtures/low_beta60_event_extension.json').read_text())
        old={'SH600000':{'instrument':'SH600000','bars':[{'date':'2025-12-30','close':'10'}],
                         'distributions':[f['old_row']]}}
        extra=copy.deepcopy(old);extra['SH600000']['bars'].append({'date':'2026-01-06','close':'11'})
        newer={**f['old_row'],'code':'sz.000937','dividPlanDate':'2026-01-02',
            'dividRegistDate':'2026-01-05','dividOperateDate':'2026-01-06',
            'dividPayDate':'2026-01-06','dividStockMarketDate':'2026-01-06',
            'dividCashPsBeforeTax':'0.1','dividReserveToStockPs':'0.1','dividCashStock':'10转1派1元'}
        extra['SZ000937']={'instrument':'SZ000937','bars':[],
            'distributions':[{**f['old_row'],'code':'sz.000937'},newer]}
        empty={'documents':[]}
        proofs={'documents':[],'unresolved_tax':{'SZ000937|2026-01-06':{'verified_exempt':False}}}
        cal=TradingCalendar(['2025-12-29','2025-12-30','2025-12-31','2026-01-05','2026-01-06'])
        return old,empty,[f['old_event']],[f['old_receipt']],extra,proofs,cal

    # Recompiling earlier rows from future-only names or overwriting original artifacts changes the old prefix.
    def test_only_new_year_events_are_appended_and_original_artifacts_stay_exact(self):
        api=self.api();args=self.inputs();before=copy.deepcopy(args[:-1])
        events,receipts,stats=api.compile_append_only(*args)
        self.assertEqual(2,len(events));self.assertEqual(args[2][0],api.serialize_event(events[0]))
        self.assertEqual(args[3][0],receipts[0]);self.assertEqual(before,args[:-1])
        self.assertEqual(1,stats['earlier_rows_of_future_only_names_ignored'])
        self.assertEqual(['SZ000937|2026-01-06'],stats['unverified_tax_event_keys'])
        self.assertEqual(Decimal('0.1'),events[1].capital_per_share)
        self.assertFalse(events[1].capital_tax_exempt_verified)
        self.assertTrue(receipts[1]['requires_zero_record_ownership_if_tax_unverified'])

    # Tampered prior artifacts, raw prefix revisions, or year-crossing record dates must not silently alter old economics.
    def test_rejects_changed_old_evidence_and_cross_boundary_record_dates(self):
        api=self.api()
        for case in ('old_event','old_receipt','raw_distribution','raw_bar','record_date'):
            with self.subTest(case=case):
                args=list(self.inputs())
                if case=='old_event':args[2][0]['cash_per_share']='0.13'
                if case=='old_receipt':args[3][0]['source_row_sha256']='0'*64
                if case=='raw_distribution':args[4]['SH600000']['distributions'][0]['dividCashPsBeforeTax']='0.13'
                if case=='raw_bar':args[4]['SH600000']['bars'][0]['close']='99'
                if case=='record_date':args[4]['SZ000937']['distributions'][1]['dividRegistDate']='2025-12-31'
                with self.assertRaises(ValueError):api.compile_append_only(*args)

    # Omitting the unresolved marker or simultaneously claiming exemption must fail before producing events.
    def test_unresolved_tax_cannot_be_hidden_or_silently_reclassified(self):
        api=self.api()
        for case in ('missing_marker','exemption','extra_marker'):
            with self.subTest(case=case):
                args=list(self.inputs())
                if case=='missing_marker':args[5]['unresolved_tax']={}
                if case=='exemption':args[5]['capital_tax']={'SZ000937|2026-01-06':{'verified_exempt':True}}
                if case=='extra_marker':args[5]['unresolved_tax']['SH600000|2026-01-06']={'verified_exempt':False}
                with self.assertRaises(ValueError):api.compile_append_only(*args)

    # Losing the account's unknown-tax guard would credit unverified capital shares for an owned position.
    def test_compiled_unknown_tax_stops_owned_account_before_mutation_but_allows_zero_inventory(self):
        api=self.api();args=self.inputs();events,_,_=api.compile_append_only(*args)
        for quantity in (0,100):
            a=StockDistributionAccount(args[-1],'1000',events)
            if quantity:a.broker.positions={'SZ000937':[{'quantity':100,'price':Decimal('10'),'bought_on':date(2025,12,29)}]}
            a.end_day(date(2026,1,5));before=copy.deepcopy((a.broker.cash,a.broker.positions,a.corporate_ledger,a.cash_claims,a.stock_claims))
            if quantity:
                with self.assertRaises(ValueError):a.start_day(date(2026,1,6))
                self.assertEqual(before,(a.broker.cash,a.broker.positions,a.corporate_ledger,a.cash_claims,a.stock_claims))
            else:
                a.start_day(date(2026,1,6));self.assertEqual({},a.owned_quantities())
                self.assertEqual(Decimal('1000'),a.broker.cash)

    def test_entry_refuses_wrong_external_plan_hash_before_any_output(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);p=base/'plan.json';p.write_text('{}\n')
            with self.assertRaises(ValueError):api.main(['--plan',str(p),'--expected-plan-sha256','0'*64,
                '--source-root',str(base),'--output-dir',str(base/'out')])
            self.assertFalse((base/'out').exists())


if __name__=='__main__':unittest.main()
