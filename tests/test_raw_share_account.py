import unittest
from datetime import date
from decimal import Decimal as D

from stock_rsi.calendar import TradingCalendar
from stock_rsi.raw_share_account import Distribution, RawShareAccount, plan_integer_targets


class RawShareAccountTests(unittest.TestCase):
    def setUp(self):
        self.calendar = TradingCalendar(["2024-06-05","2024-06-06","2024-06-07","2024-06-11"])

    def owned(self,events=()):
        account = RawShareAccount(self.calendar,"20000",events,tax_reserve_rate=".2")
        account.broker.cash = D("9995")
        account.broker.positions = {"A":[{"quantity":1000,"price":D("10"),"bought_on":date(2024,6,5)}]}
        return account

    def test_price_or_factor_changes_never_change_raw_inventory(self):
        account = self.owned()
        self.assertEqual(account.wealth({"A":D("10")})["equity"],D("19995"))
        self.assertEqual(account.wealth({"A":D("8.32")})["equity"],D("18315"))
        self.assertEqual(account.owned_quantities(),{"A":1000})
        orders = plan_integer_targets(D("100000"),{"A":1000},{"B":D(".95")},{"B":D("10")})
        self.assertEqual(orders,(("SELL","A",1000),("BUY","B",9500)))

    def test_cash_distribution_is_a_receivable_before_it_is_spendable(self):
        event = Distribution("d","A",date(2024,6,1),date(2024,6,6),date(2024,6,7),
                             date(2024,6,7),None,D(".2309"),D("0"),False)
        account = self.owned([event])
        account.end_day(date(2024,6,6))
        account.start_day(date(2024,6,7))
        self.assertEqual(account.broker.cash,D("9995"))
        nav=account.wealth({"A":D("9.7691")})
        self.assertEqual(nav["cash_receivable"],D("184.72"))
        self.assertEqual(nav["equity"],D("19948.82"))
        account.start_day(date(2024,6,11))
        self.assertEqual(account.broker.cash,D("10179.72"))
        self.assertEqual(account.wealth({"A":D("9.7691")})["cash_receivable"],D("0"))
        account.start_day(date(2024,6,11))
        self.assertEqual(account.broker.cash,D("10179.72"))

    def test_buying_after_record_date_does_not_create_dividend_income(self):
        event = Distribution("d","A",date(2024,6,1),date(2024,6,6),date(2024,6,7),
                             date(2024,6,7),None,D("1"),D("0"),False)
        account = RawShareAccount(self.calendar,"20000",[event])
        account.end_day(date(2024,6,6))
        account.broker.positions = {"A":[{"quantity":1000,"price":D("10"),"bought_on":date(2024,6,7)}]}
        account.start_day(date(2024,6,7))
        self.assertEqual(account.wealth({"A":D("10")})["cash_receivable"],D("0"))

    def test_capital_shares_wait_for_listing_and_preserve_total_wealth(self):
        event = Distribution("s","A",date(2024,6,1),date(2024,6,6),date(2024,6,7),
                             None,date(2024,6,11),D("0"),D(".2"),True)
        account = self.owned([event])
        account.end_day(date(2024,6,6))
        account.start_day(date(2024,6,7))
        self.assertEqual(sum(l['quantity'] for l in account.broker.positions['A']),1000)
        self.assertEqual(account.owned_quantities(),{"A":1200})
        self.assertAlmostEqual(account.wealth({"A":D("10")/D("1.2")})["equity"],D("19995"),places=10)
        account.start_day(date(2024,6,11))
        self.assertEqual(sum(l['quantity'] for l in account.broker.positions['A']),1200)
        self.assertTrue(all(type(l['quantity']) is int for l in account.broker.positions['A']))
        self.assertTrue(all(l['bought_on']<date(2024,6,11) for l in account.broker.positions['A']))

    def test_unknown_or_fractional_capital_credit_fails_closed(self):
        for ratio,verified in ((D(".2"),False),(D(".0005"),True)):
            event = Distribution("s","A",date(2024,6,1),date(2024,6,6),date(2024,6,7),
                                 None,date(2024,6,7),D("0"),ratio,verified)
            account = self.owned([event])
            account.end_day(date(2024,6,6))
            with self.assertRaises(ValueError):account.start_day(date(2024,6,7))
