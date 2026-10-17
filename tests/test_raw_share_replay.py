import copy
import unittest
from decimal import Decimal

from stock_rsi.calendar import TradingCalendar
from scripts.run_low_risk_raw_share_validation import canonical_distributions, simulate_fixed_targets


class RawShareReplayTests(unittest.TestCase):
    def test_future_market_data_does_not_change_prior_snapshot_or_integer_orders(self):
        calendar=TradingCalendar(["2023-12-29","2024-01-02","2024-01-03"])
        def row(day,price):
            return {"date":day,"code":"sh.600004","open":str(price),"high":str(price),
                    "low":str(price),"close":str(price),"preclose":"10","volume":"1000000",
                    "amount":"10000000","tradestatus":"1","isST":"0","adjustflag":"3"}
        bars={"SH600004":{day:row(day,10) for day in ("2023-12-29","2024-01-02","2024-01-03")}}
        targets={"2024-01-02":{"as_of":"2023-12-29","weights":{"SH600004":.95}}}
        first=simulate_fixed_targets(calendar,bars,(),targets,"100000")
        changed=copy.deepcopy(bars)
        changed["SH600004"]["2024-01-03"]=row("2024-01-03",20)
        second=simulate_fixed_targets(calendar,changed,(),targets,"100000")
        self.assertEqual(first["intents"][0],second["intents"][0])
        self.assertEqual(first["fills"][0]["quantity"],9500)
        self.assertEqual(first["days"][-1]["equity"],Decimal("99952.50"))
        self.assertGreater(second["days"][-1]["equity"],first["days"][-1]["equity"])

    def test_joint_distribution_correction_requires_expected_vendor_value(self):
        row={"code":"sh.600720","dividPlanDate":"2024-06-04","dividRegistDate":"2024-06-12",
             "dividOperateDate":"2024-06-13","dividPayDate":"2024-06-13","dividStockMarketDate":"",
             "dividCashPsBeforeTax":"0.257","dividStocksPs":"0","dividReserveToStockPs":""}
        proofs={"cash_overrides":{"SH600720|2024-06-13":{"expected_source_cash_per_share":"0.257",
                  "cash_per_share":"0.3674","publication_day":"2024-06-04"}},"capital_tax":{}}
        values=canonical_distributions({"SH600720":{"distributions":[row]}},proofs)
        self.assertEqual(values[0].cash_per_share,Decimal("0.3674"))
        row["dividCashPsBeforeTax"]="0.3"
        with self.assertRaisesRegex(ValueError,"override"):
            canonical_distributions({"SH600720":{"distributions":[row]}},proofs)
