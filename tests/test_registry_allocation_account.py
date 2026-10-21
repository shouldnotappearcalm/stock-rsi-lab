"""Synthetic registry-envelope subclass tests; no actual source or replay."""
import copy
import importlib
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal as D
from functools import partial
from stock_rsi.calendar import TradingCalendar
from stock_rsi.models import Decision
from stock_rsi.stock_distribution_account import StockDistribution,StockDistributionAccount
from stock_rsi.execution_cost import ExecutionCostBroker

class RegistryAllocationAccountTests(unittest.TestCase):
    def api(self):return importlib.import_module('stock_rsi.registry_allocation_account')
    def setUp(self):
        self.cal=TradingCalendar(['2024-05-28','2024-06-03','2024-06-04','2024-06-05','2024-06-06','2024-06-07'])
        self.event=StockDistribution('synthetic','SZ002831',date(2024,5,28),date(2024,6,3),date(2024,6,4),date(2024,6,4),date(2024,6,6),D('.8038127'),D('.4019063'),True)
        self.proof={'contract':'PRIMARY_LARGEST_REMAINDER_LOCAL_ENVELOPE_V1','issuer':'SZ002831','event_id':'synthetic',
            'record_date':'2024-06-03','ex_date':'2024-06-04','component':'capital','source_file':'synthetic.pdf','source_sha256':'a'*64,
            'published_on':'2024-05-28','available_at':'2024-05-29T00:00:00+08:00','actual_arrival_verified':False,
            'eligible_count':10000000,'declared_total_shares':4019063,'quoted_per10':'4.019063',
            'fraction_method':'LARGEST_REMAINDER_DESC_RANDOM_TIES','quoted_precision_bound':'ONE_LAST_DIGIT_SYMMETRIC_ENGINEERING_ASSUMPTION'}
    def make(self,choice=None,proof=None,events=None,quantity=900,component='capital'):
        module=self.api();proof=self.proof if proof is None else proof
        account=module.RegistryAllocationAccount(self.cal,'10000',(self.event,) if events is None else events,
            registry_proofs={'synthetic':{component:proof}},allocation_choices={} if choice is None else {'synthetic':{component:choice}},
            broker_factory=partial(ExecutionCostBroker,extra_cost_bps=20))
        if quantity:account.broker.positions={'SZ002831':[{'quantity':quantity//2,'price':D('10'),'bought_on':date(2024,5,28)},{'quantity':quantity-quantity//2,'price':D('11'),'bought_on':date(2024,5,28)}]}
        account.start_day(date(2024,6,3));account.end_day(date(2024,6,3));return account
    def state(self,a):
        return copy.deepcopy({k:(v.days if k=='calendar' else {bk:(bv.days if bk=='calendar' else bv) for bk,bv in v.__dict__.items()} if k=='broker' else v) for k,v in a.__dict__.items()})

    def test_missing_choice_atomic_even_when_positive_payment_due(self):
        m=self.api();a=self.make();a.cash_claims.append({'event_id':'earlier','net':D('2'),'available_on':date(2024,6,4),'paid':False})
        before=self.state(a)
        with self.assertRaises(m.AllocationChoiceRequired) as captured:a.start_day(date(2024,6,4))
        err=captured.exception
        self.assertEqual((err.event_id,err.instrument,err.component,err.registered_quantity),('synthetic','SZ002831','capital',900))
        self.assertEqual(err.candidates,(361,362));self.assertEqual(err.envelope['possible_integer_shares'],[361,362])
        self.assertEqual(self.state(a),before)

    def test_selected_entire_account_quantities_pending_listing_cash_and_t1_fees(self):
        for chosen in (361,362):
            a=self.make(chosen);original=copy.deepcopy((a.events,a.entitlements));a.start_day(date(2024,6,4))
            self.assertEqual(a.broker.positions['SZ002831'][0]['quantity'],450)
            self.assertEqual(a.owned_quantities(),{'SZ002831':900+chosen})
            self.assertEqual(a.stock_claims[0]['quantity'],chosen);self.assertFalse(a.stock_claims[0]['credited'])
            self.assertEqual(a.allocation_audit[0]['nominal_entitlement'],'361.7156700')
            self.assertEqual(a.allocation_audit[0]['candidates'],[361,362])
            self.assertEqual(a.allocation_audit[0]['chosen_integer_quantity'],chosen)
            self.assertNotIn('allocation_audit',a.wealth({'SZ002831':'10'}))
            self.assertEqual((a.events,a.entitlements),original)
            a.end_day(date(2024,6,4));a.start_day(date(2024,6,5))
            self.assertTrue(a.cash_claims[0]['paid']);a.end_day(date(2024,6,5))
            a.broker.submit(Decision('SELL','SZ002831',chosen,('synthetic',),'test','snapshot'),self.cal.at(date(2024,6,5),'15:05:00'),self.cal.at(date(2024,6,6),'09:30:00'))
            a.start_day(date(2024,6,6));self.assertTrue(a.stock_claims[0]['credited'])
            self.assertEqual(a.broker.positions['SZ002831'][-1],{'quantity':chosen,'bought_on':date(2024,6,3),'price':D(0)})
            a.broker.on_market_open([{'security_id':'SZ002831','trade_date':'2024-06-06','suspended':False,'open':'10','limit_up':'11','limit_down':'9'}])
            fill=a.broker.fills[-1];self.assertEqual(fill['quantity'],chosen)
            expected=max(D(5),D(10)*chosen*D('.0015')).quantize(D('.01'))+(D(10)*chosen*D('.002')).quantize(D('.01'))
            self.assertEqual(D(fill['cost']),expected);self.assertEqual(a.owned_quantities(),{'SZ002831':900})
            self.assertEqual(len(a.allocation_audit),1)

    def test_invalid_choice_bool_or_nonmember_is_atomic_and_no_proof_is_old_failure(self):
        for choice in (True,360,363,'361'):
            with self.subTest(choice=choice):
                try:a=self.make(choice)
                except ValueError:continue
                before=self.state(a)
                with self.assertRaises(ValueError):a.start_day(date(2024,6,4))
                self.assertEqual(self.state(a),before)
        a=self.api().RegistryAllocationAccount(self.cal,'10000',[self.event])
        a.entitlements={'synthetic':900};before=self.state(a)
        with self.assertRaisesRegex(ValueError,'fractional'):a.start_day(date(2024,6,4))
        self.assertEqual(self.state(a),before)

    def test_proof_identity_ratio_dates_availability_hash_and_orphan_rejected(self):
        for key,value in [('issuer','SH600000'),('event_id','other'),('component','stock'),('record_date','2024-06-02'),
                          ('ex_date','2024-06-05'),('published_on','2024-05-27'),('quoted_per10','4.019064'),
                          ('available_at','2024-06-04T10:00:00+08:00'),('source_sha256','invalid')]:
            p=copy.deepcopy(self.proof);p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.make(361,proof=p)
        m=self.api()
        for proofs,choices in [({'other':{'capital':self.proof}},{}),({}, {'other':{'capital':361}}),
                              ({'synthetic':{'cash':self.proof}},{}),({}, {'synthetic':{'capital':361}})]:
            with self.assertRaises(ValueError):m.RegistryAllocationAccount(self.cal,'10000',[self.event],registry_proofs=proofs,allocation_choices=choices)

    def test_all_current_unknown_tax_and_reserve_guards_precede_choice(self):
        m=self.api()
        for event in [replace(self.event,capital_tax_exempt_verified=False),
                      replace(self.event,capital_per_share=D(0),stock_per_share=D('.4019063'),stock_tax_basis_verified=False,stock_taxable_income_per_share=D('.4'))]:
            p=copy.deepcopy(self.proof);component='stock' if event.stock_per_share else 'capital';p['component']=component
            a=self.make(proof=p,events=[event],component=component);before=self.state(a)
            with self.assertRaises(ValueError) as err:a.start_day(date(2024,6,4))
            self.assertNotIsInstance(err.exception,m.AllocationChoiceRequired);self.assertIn('unverified',str(err.exception));self.assertEqual(self.state(a),before)
        later=replace(self.event,event_id='later',capital_per_share=D('.4'),capital_tax_exempt_verified=False)
        a=self.make(events=[self.event,later]);before=self.state(a)
        with self.assertRaisesRegex(ValueError,'unverified') as err:a.start_day(date(2024,6,4))
        self.assertNotIsInstance(err.exception,m.AllocationChoiceRequired);self.assertEqual(self.state(a),before)
        stock=replace(self.event,capital_per_share=D(0),stock_per_share=D('.4019063'),stock_tax_basis_verified=True,stock_taxable_income_per_share=D('10'))
        p=copy.deepcopy(self.proof);p['component']='stock';a=self.make(proof=p,events=[stock],component='stock');before=self.state(a)
        with self.assertRaisesRegex(ValueError,'exceeds cash'):a.start_day(date(2024,6,4))
        self.assertEqual(self.state(a),before)

    def test_integer_and_zero_events_exact_old_financial_behavior_without_extra_audit(self):
        m=self.api();event=replace(self.event,capital_per_share=D('.4'))
        for quantity in (0,900):
            new=m.RegistryAllocationAccount(self.cal,'10000',[event]);old=StockDistributionAccount(self.cal,'10000',[event])
            for a in (new,old):
                if quantity:a.broker.positions={'SZ002831':[{'quantity':quantity,'price':D(10),'bought_on':date(2024,5,28)}]}
            for day in self.cal.days[1:]:
                for a in (new,old):a.start_day(day);a.end_day(day)
                for key in ('cash_claims','stock_claims','corporate_ledger','entitlements','_processed','_last_clock'):self.assertEqual(getattr(new,key),getattr(old,key))
                for key in ('cash','positions','orders','fills'):self.assertEqual(getattr(new.broker,key),getattr(old.broker,key))
                self.assertEqual(new.wealth({'SZ002831':'10'}),old.wealth({'SZ002831':'10'}))
            self.assertEqual(new.allocation_audit,[])
        a=self.make(quantity=0);a.start_day(date(2024,6,4));self.assertEqual(a.allocation_audit,[]);self.assertEqual(a.owned_quantities(),{})

    def test_stock_component_audit_and_no_per_lot_rounding(self):
        event=replace(self.event,capital_per_share=D(0),stock_per_share=D('.4019063'),stock_tax_basis_verified=True,stock_taxable_income_per_share=D('.4'))
        p=copy.deepcopy(self.proof);p['component']='stock';a=self.make(361,proof=p,events=[event],component='stock')
        a.start_day(date(2024,6,4));self.assertEqual(a.stock_claims[0]['share_kind'],'STOCK_DIVIDEND')
        self.assertEqual(a.stock_claims[0]['quantity'],361)
        self.assertEqual(a.corporate_ledger[-1]['stock_shares'],361)
        self.assertEqual(a.allocation_audit[0]['registered_quantity'],900)
        self.assertEqual(a.allocation_audit[0]['envelope']['rounding_scope'],'ENTIRE_REGISTERED_ACCOUNT_NOT_FIFO_LOTS')
        self.assertIs(a.allocation_audit[0]['envelope']['actual_registry_allocation_certified'],False)

    def test_second_fractional_component_choice_missing_retains_entire_precredit_state(self):
        m=self.api();event=replace(self.event,stock_per_share=D('.4019063'),stock_tax_basis_verified=True,stock_taxable_income_per_share=D('.4'))
        stock_proof=copy.deepcopy(self.proof);stock_proof['component']='stock'
        a=m.RegistryAllocationAccount(self.cal,'10000',[event],registry_proofs={'synthetic':{'capital':self.proof,'stock':stock_proof}},allocation_choices={'synthetic':{'capital':361}})
        a.entitlements={'synthetic':900};a.cash_claims.append({'event_id':'due','net':D('9'),'available_on':date(2024,6,4),'paid':False})
        before=self.state(a)
        with self.assertRaises(m.AllocationChoiceRequired) as err:a.start_day(date(2024,6,4))
        self.assertEqual(err.exception.component,'stock');self.assertEqual(self.state(a),before)
        self.assertEqual(a.allocation_audit,[])

    def test_inputs_immutable_repeated_start_no_duplicate_and_integer_choice_no_override(self):
        proofs={'synthetic':{'capital':copy.deepcopy(self.proof)}};choices={'synthetic':{'capital':361}};before=copy.deepcopy((proofs,choices))
        a=self.api().RegistryAllocationAccount(self.cal,'10000',[self.event],registry_proofs=proofs,allocation_choices=choices)
        a.entitlements={'synthetic':900};a.start_day(date(2024,6,4));state=self.state(a);a.start_day(date(2024,6,4))
        self.assertEqual(self.state(a),state);self.assertEqual((proofs,choices),before)
        integer=replace(self.event,capital_per_share=D('.4'));p=copy.deepcopy(self.proof);p.update(quoted_per10='4.000000',declared_total_shares=4000000)
        a=self.make(360,proof=p,events=[integer]);a.start_day(date(2024,6,4));self.assertEqual(a.allocation_audit,[])
        a=self.make(361,proof=p,events=[integer]);state=self.state(a)
        with self.assertRaises(ValueError):a.start_day(date(2024,6,4))
        self.assertEqual(self.state(a),state)

if __name__=='__main__':unittest.main()
