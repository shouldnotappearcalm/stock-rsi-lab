import copy
from dataclasses import replace
from datetime import date
from decimal import Decimal as D
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from stock_rsi.calendar import TradingCalendar
from stock_rsi.stock_distribution_account import StockDistribution, StockDistributionAccount

class IssuerScheduleTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('stock_rsi.issuer_schedule_account')
        except ModuleNotFoundError:self.fail('separate explicitly conditional issuer-schedule account absent')
    def fixture(self):
        api=self.api();repo=Path(__file__).resolve().parents[1]
        registry=json.loads((repo/'experiments/qlib/low-beta60-issuer-schedule-scenario.json').read_bytes())
        row=registry['event'];event=StockDistribution(**{k:date.fromisoformat(v) if k in ('announced','recorded','ex_date','pay_date','listed') else D(v) if k in ('cash_per_share','capital_per_share','stock_per_share','stock_taxable_income_per_share') else v for k,v in row.items()})
        cal=TradingCalendar(['2026-06-15','2026-06-16','2026-06-17','2026-06-18'])
        return api,registry,event,cal
    def owned(self, cls, cal, events, **kw):
        a=cls(cal,'20000',events,**kw);a.broker.cash=D('5000');a.broker.positions={'SZ000937':[{'quantity':6300,'price':D('2'),'bought_on':date(2026,6,15)}]};a.end_day(date(2026,6,16));return a
    def evidence(self,api,reg,event,tmp):
        root=Path(tmp);source=root/'source';repo=root/'repo'
        # Use genuine reviewed extraction values, and distinct local synthetic bodies for unit-level byte binding.
        for mapping,parent in ((reg['source_sha256'],source),(reg['public_evidence_sha256'],repo)):
            for name in mapping:
                f=parent/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(name);mapping[name]=api.file_sha(f)
        return api.load_schedule_evidence(reg,source,repo,[event]),source,repo
    def test_owned6300_credit630_and_reserve126_without_false_statutory_flag_or_double_credit(self):
        api,reg,event,cal=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            ev,_,_=self.evidence(api,reg,event,d);a=self.owned(api.IssuerScheduleAccount,cal,[event],schedule_evidence=ev)
            a.start_day(date(2026,6,17));a.start_day(date(2026,6,17))
            self.assertFalse(event.capital_tax_exempt_verified);self.assertEqual(a.events,(event,));self.assertEqual(a.owned_quantities()['SZ000937'],6930)
            self.assertEqual(a.cash_claims[0]['reserve'],D('126'));self.assertEqual(a.cash_claims[0]['net'],D('504'));self.assertEqual(a.broker.cash,D('5000'))
            self.assertEqual(len(a.scenario_ledger),1);self.assertFalse(a.scenario_ledger[0]['statutory_exemption_verified'])
            a.end_day(date(2026,6,17));a.start_day(date(2026,6,18));self.assertEqual(a.broker.cash,D('5504'))
            original=self.owned(StockDistributionAccount,cal,[event]);before=copy.deepcopy(original.__dict__)
            with self.assertRaisesRegex(ValueError,'capital transfer tax'):original.start_day(date(2026,6,17))
            self.assertEqual(original.cash_claims,[]);self.assertEqual(original.owned_quantities()['SZ000937'],6300)
    def test_evidence_rejects_wrong_investor_changed_event_and_body_tampering(self):
        api,reg,event,cal=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            ev,source,repo=self.evidence(api,reg,event,d)
            for key,val in (('investor_scope','CORPORATE'),('statutory_exemption_verified',True),('retrospective_evidence_evaluator_only',False)):
                changed=copy.deepcopy(reg);changed[key]=val
                with self.assertRaises(ValueError):api.load_schedule_evidence(changed,source,repo,[event])
            with self.assertRaises(ValueError):api.load_schedule_evidence(reg,source,repo,[replace(event,cash_per_share=D('.2'))])
            (source/next(iter(reg['source_sha256']))).write_bytes(b'changed')
            with self.assertRaises(ValueError):api.load_schedule_evidence(reg,source,repo,[event])
    def test_mixed_unknown_event_and_fractional_entitlement_fail_before_any_batch_mutation(self):
        api,reg,event,cal=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            ev,_,_=self.evidence(api,reg,event,d)
            for bad in (replace(event,event_id='other'),replace(event,event_id='fractional',capital_per_share=D('.00001'),capital_tax_exempt_verified=True)):
                a=self.owned(api.IssuerScheduleAccount,cal,[event,bad],schedule_evidence=ev)
                before=copy.deepcopy((a.broker.cash,a.broker.positions,a.corporate_ledger,a.cash_claims,a.stock_claims,a.scenario_ledger))
                with self.assertRaises(ValueError):a.start_day(date(2026,6,17))
                self.assertEqual(before,(a.broker.cash,a.broker.positions,a.corporate_ledger,a.cash_claims,a.stock_claims,a.scenario_ledger))
    def test_without_supported_event_original_financial_behavior_is_identical(self):
        api,reg,event,cal=self.fixture();cash=replace(event,event_id='cash',capital_per_share=D(0))
        a=self.owned(api.IssuerScheduleAccount,cal,[cash],schedule_evidence=None);b=self.owned(StockDistributionAccount,cal,[cash])
        for day in (date(2026,6,17),date(2026,6,18)):
            a.start_day(day);b.start_day(day);a.end_day(day);b.end_day(day)
        for key in ('corporate_ledger','cash_claims','stock_claims','entitlements'):self.assertEqual(getattr(a,key),getattr(b,key))
        self.assertEqual(a.broker.cash,b.broker.cash);self.assertEqual(a.broker.positions,b.broker.positions);self.assertEqual(a.scenario_ledger,[])

if __name__=='__main__':unittest.main()
