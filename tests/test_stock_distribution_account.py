import copy
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal as D
from stock_rsi.calendar import TradingCalendar
from stock_rsi.raw_share_account import Distribution,RawShareAccount
try:
    from stock_rsi.stock_distribution_account import StockDistribution,StockDistributionAccount
except ImportError:StockDistribution=StockDistributionAccount=None


class StockDistributionAccountTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(StockDistributionAccount)
        self.cal=TradingCalendar(['2024-06-25','2024-06-26','2024-06-27','2024-06-28','2024-07-01'])

    def event(self,**changes):
        return replace(StockDistribution('s','A',date(2024,6,21),date(2024,6,26),date(2024,6,27),
            date(2024,6,27),date(2024,6,28),D('.1'),D('0'),False,
            stock_per_share=D('.4'),stock_taxable_income_per_share=D('.4'),stock_tax_basis_verified=True),**changes)

    def owned(self,events,cls=None):
        a=(cls or StockDistributionAccount)(self.cal,'20000',events,tax_reserve_rate='.2')
        a.broker.cash=D('5895');a.broker.positions={'A':[{'quantity':1000,'price':D('14.1'),'bought_on':date(2024,6,25)}]}
        return a

    def test_cash_and_stock_income_share_the_stress_tax_base_and_listing_is_separate(self):
        a=self.owned([self.event()]);self.assertEqual(a.wealth({'A':D('14.1')})['equity'],D('19995'))
        a.end_day(date(2024,6,26));a.start_day(date(2024,6,27))
        self.assertEqual(a.owned_quantities(),{'A':1400})
        self.assertEqual(sum(x['quantity'] for x in a.broker.positions['A']),1000)
        w=a.wealth({'A':D('10')});self.assertEqual(w['cash_receivable'],D('0'))
        self.assertEqual(w['pending_stock_value'],D('4000'));self.assertEqual(w['equity'],D('19895'))
        ex=[r for r in a.corporate_ledger if r['kind']=='EX_DATE_ENTITLEMENT'][0]
        self.assertEqual((ex['stock_shares'],ex['capital_shares'],ex['cash_gross'],ex['taxable_stock_income'],ex['stress_tax_reserve']),
            (400,0,D('100'),D('400'),D('100')))
        a.start_day(date(2024,6,28));a.start_day(date(2024,6,28))
        self.assertEqual(sum(x['quantity'] for x in a.broker.positions['A']),1400)
        self.assertEqual(a.broker.cash,D('5895'));self.assertEqual(a.wealth({'A':D('10')})['equity'],D('19895'))

    def test_unknown_tax_fractional_shares_or_unfunded_tax_reject_before_batch_changes(self):
        bads=[self.event(stock_tax_basis_verified=False),self.event(stock_per_share=D('.0005')),
            self.event(cash_per_share=D('.01')),
            self.event(stock_per_share=D('0'),stock_taxable_income_per_share=D('0'),capital_per_share=D('.4'),capital_tax_exempt_verified=False)]
        for bad in bads:
            good=self.event(event_id='cash',stock_per_share=D('0'),stock_taxable_income_per_share=D('0'),cash_per_share=D('1'))
            a=self.owned([good,bad]);a.end_day(date(2024,6,26))
            before=copy.deepcopy((a.broker.cash,a.broker.positions,a.corporate_ledger,a.cash_claims,a.stock_claims))
            with self.assertRaises(ValueError):a.start_day(date(2024,6,27))
            self.assertEqual((a.broker.cash,a.broker.positions,a.corporate_ledger,a.cash_claims,a.stock_claims),before)

    def test_zero_record_date_inventory_does_not_grant_shares_or_require_fictitious_tax_proof(self):
        a=StockDistributionAccount(self.cal,'20000',[self.event(stock_tax_basis_verified=False)])
        a.end_day(date(2024,6,26));a.start_day(date(2024,6,27))
        self.assertEqual(a.owned_quantities(),{});self.assertEqual(a.broker.cash,D('20000'))
        self.assertEqual(a.cash_claims,[]);self.assertEqual(a.stock_claims,[])

    def test_stock_only_timing_and_amounts_are_validated_at_construction(self):
        for changes in ({'listed':None},{'listed':date(2024,6,25)}, {'stock_per_share':D('-1')},
                        {'stock_per_share':D('NaN')},{'stock_taxable_income_per_share':D('-1')}):
            with self.assertRaises(ValueError):self.owned([self.event(**changes)])

    def test_legacy_cash_and_capital_financial_state_is_unchanged(self):
        event=Distribution('c','A',date(2024,6,21),date(2024,6,26),date(2024,6,27),date(2024,6,27),
            date(2024,6,28),D('.1'),D('.4'),True)
        old=self.owned([event],RawShareAccount);new=self.owned([event])
        for day in self.cal.days:
            for a in (old,new):a.start_day(day)
            self.assertEqual(old.wealth({'A':D('10')}),new.wealth({'A':D('10')}))
            self.assertEqual(old.owned_quantities(),new.owned_quantities())
            for a in (old,new):a.end_day(day)
