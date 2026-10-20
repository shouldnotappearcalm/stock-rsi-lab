import copy
import hashlib
import json
from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stock_rsi.calendar import TradingCalendar
from stock_rsi.stock_distribution_account import StockDistribution, StockDistributionAccount
try:
    from stock_rsi.capital_income_stress_account import CapitalIncomeStressAccount, load_capital_income_basis
except ImportError:
    CapitalIncomeStressAccount = load_capital_income_basis = None


class CapitalIncomeStressTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(CapitalIncomeStressAccount)
        self.cal = TradingCalendar(['2025-06-25', '2025-06-26', '2025-06-27', '2025-06-30', '2025-07-01'])
        self.event = StockDistribution('e', 'SH600580', date(2025,6,20), date(2025,6,26), date(2025,6,27),
            date(2025,6,27), date(2025,6,27), D('.15'), D('.2'), False)
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        (self.root/'annual.pdf').write_bytes(b'synthetic annual source; RMB1000 capital')
        (self.root/'proposal.pdf').write_bytes(b'synthetic proposal; 1000 ordinary shares')
        self.registry = {'status':'COUNTERFACTUAL_PAR_VALUE_BASIS_NOT_TAX_EXEMPTION', 'events':[{
            'event_id':'e','instrument':'SH600580','recorded':'2025-06-26','ex_date':'2025-06-27',
            'event_sha256':self.event_sha(self.event),'issuer':'Synthetic Issuer','nominal_capital_CNY':'1000',
            'ordinary_shares':1000,'par_value_CNY':'1','sources':[
                self.source('annual.pdf','nominal_capital',{'currency':'CNY','unit_multiplier':'1','nominal_capital':'1000'}),
                self.source('proposal.pdf','ordinary_shares',{'unit':'shares','ordinary_shares':1000})]}]}

    def event_sha(self, event):
        return hashlib.sha256(json.dumps(asdict(event),sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

    def source(self, name, role, extracted):
        return {'file':name,'sha256':hashlib.sha256((self.root/name).read_bytes()).hexdigest(),'role':role,
                'instrument':'SH600580','issuer':'Synthetic Issuer','publication_day':'2025-04-26','page':1,'extracted':extracted}

    def owned(self, events=None, registry=None, cls=None, quantity=1100):
        events = tuple(events or [self.event]); cls = cls or CapitalIncomeStressAccount
        kwargs = {} if cls is StockDistributionAccount else {'capital_income_basis':load_capital_income_basis(
            self.registry if registry is None else registry, self.root, events)}
        a = cls(self.cal,'20000',events,tax_reserve_rate='.2',**kwargs)
        a.broker.cash=D('10000'); a.broker.positions={'SH600580':[{'quantity':quantity,'bought_on':date(2025,6,25),'price':D('9')}]}
        return a

    def state(self,a):
        return copy.deepcopy((a.broker.cash,a.broker.positions,a.cash_claims,a.stock_claims,a.corporate_ledger,a._last_clock,a._processed))

    def test_full_par_reserve_and_physical_capital_credit_preserve_unknown_exemption(self):
        a=self.owned(); a.end_day(date(2025,6,26)); a.start_day(date(2025,6,27))
        row=[r for r in a.corporate_ledger if r['kind']=='EX_DATE_ENTITLEMENT'][0]
        self.assertEqual((row['cash_gross'],row['taxable_capital_stress_income'],row['stress_tax_reserve'],row['capital_shares'],row['stock_shares']),
                         (D('165'),D('220'),D('77'),220,0))
        self.assertEqual(a.wealth({'SH600580':D('9')})['cash_receivable'],D('88'))
        self.assertEqual(a.owned_quantities(),{'SH600580':1320})
        self.assertEqual(a.capital_stress_ledger[0]['additional_scenario_reserve_CNY'],D('44'))
        self.assertFalse(a.events[0].capital_tax_exempt_verified)
        self.assertEqual(a.stock_claims[0]['share_kind'],'CAPITAL_TRANSFER')
        a.start_day(date(2025,6,30));a.start_day(date(2025,6,30))
        self.assertEqual(a.broker.cash,D('10088')); self.assertEqual(a.owned_quantities(),{'SH600580':1320})

    def test_missing_basis_with_nonzero_entitlement_still_rejects_atomically(self):
        a=self.owned(registry={'status':self.registry['status'],'events':[]});a.end_day(date(2025,6,26));before=self.state(a)
        with self.assertRaisesRegex(ValueError,'unverified'):a.start_day(date(2025,6,27))
        self.assertEqual(self.state(a),before)

    def test_bad_identity_future_source_units_amounts_or_changed_bytes_cannot_authorize_scenario(self):
        mutations=[lambda r:r['events'][0].update(instrument='SH600581'),
            lambda r:r['events'][0].update(ex_date='2025-06-30'),
            lambda r:r['events'][0].update(event_sha256='0'*64),
            lambda r:r['events'][0]['sources'][0].update(publication_day='2025-08-12'),
            lambda r:r['events'][0]['sources'][0].update(issuer='Other Issuer'),
            lambda r:r['events'][0]['sources'][0]['extracted'].update(currency='USD'),
            lambda r:r['events'][0]['sources'][1]['extracted'].update(unit='lots'),
            lambda r:r['events'][0].update(par_value_CNY='2'),
            lambda r:r['events'][0].update(ordinary_shares=1001),
            lambda r:r['events'][0]['sources'][0].update(sha256='0'*64)]
        for mutate in mutations:
            r=copy.deepcopy(self.registry);mutate(r)
            with self.subTest(registry=r):
                with self.assertRaises(ValueError):self.owned(registry=r)

    def test_fractional_or_unfunded_same_day_batch_has_no_payments_or_partial_credits(self):
        for event,quantity in [(replace(self.event,cash_per_share=D('.01')),1100),(self.event,1101),
                (replace(self.event,stock_per_share=D('.1'),stock_tax_basis_verified=False),1100)]:
            r=copy.deepcopy(self.registry);r['events'][0]['event_sha256']=self.event_sha(event)
            a=self.owned(events=[event],registry=r,quantity=quantity);a.end_day(date(2025,6,26))
            a.cash_claims.append({'event_id':'prior','available_on':date(2025,6,27),'paid':False,'net':D('10')})
            before=self.state(a)
            with self.assertRaises(ValueError):a.start_day(date(2025,6,27))
            self.assertEqual(self.state(a),before);self.assertEqual(a.capital_stress_ledger,[])

    def test_verified_exempt_and_zero_unknown_states_are_identical_to_old_account(self):
        empty={'status':self.registry['status'],'events':[]}
        for event,quantity in [(replace(self.event,capital_tax_exempt_verified=True),1100),(self.event,0)]:
            old=self.owned(events=[event],cls=StockDistributionAccount,quantity=quantity)
            new=self.owned(events=[event],registry=empty,quantity=quantity)
            if quantity==0:old.broker.positions=new.broker.positions={}
            for day in self.cal.days:
                for a in (old,new):a.start_day(day)
                self.assertEqual(self.state(old),self.state(new)); self.assertEqual(old.wealth({'SH600580':D('9')}),new.wealth({'SH600580':D('9')}))
                for a in (old,new):a.end_day(day)
            self.assertEqual(new.capital_stress_ledger,[])

    def test_extra_reserve_affects_future_available_cash_without_rewriting_past_intent(self):
        old=self.owned(events=[replace(self.event,capital_tax_exempt_verified=True)],cls=StockDistributionAccount)
        new=self.owned()
        for a in (old,new):a.end_day(date(2025,6,26))
        self.assertEqual(old.broker.cash,new.broker.cash)
        for a in (old,new):a.start_day(date(2025,6,27));a.start_day(date(2025,6,30))
        self.assertEqual(old.broker.cash-new.broker.cash,D('44'))
        # One future whole lot at101.10 plus5 cost is affordable only without the extra reserve.
        from stock_rsi.models import Decision
        for a in (old,new):
            a.broker.replace_pending_intent([Decision('BUY','SH600580',100,('s',),'future test','synthetic')],
                self.cal.at(date(2025,6,30),'15:05:00'),self.cal.at(date(2025,7,1),'09:30:00'))
            a.broker.on_market_open([{'security_id':'SH600580','trade_date':'2025-07-01','open':'101.10','limit_up':'120','limit_down':'80','suspended':False}])
        self.assertEqual(len(old.broker.fills),1);self.assertEqual(new.broker.fills,[])
