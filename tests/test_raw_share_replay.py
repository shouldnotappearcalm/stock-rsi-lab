import copy
import unittest
from decimal import Decimal

from stock_rsi.calendar import TradingCalendar
from scripts.run_low_risk_raw_share_validation import canonical_distributions, simulate_fixed_targets, validate_source_coverage


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
             "dividCashPsBeforeTax":"0.257","dividStocksPs":"0","dividReserveToStockPs":"0"}
        proofs={"cash_overrides":{"SH600720|2024-06-13":{"expected_source_cash_per_share":"0.257",
                  "cash_per_share":"0.3674","publication_day":"2024-06-04"}},"capital_tax":{}}
        values=canonical_distributions({"SH600720":{"distributions":[row]}},proofs)
        self.assertEqual(values[0].cash_per_share,Decimal("0.3674"))
        row["dividCashPsBeforeTax"]="0.3"
        with self.assertRaisesRegex(ValueError,"override"):
            canonical_distributions({"SH600720":{"distributions":[row]}},proofs)


class RawSourceAdmissionTests(unittest.TestCase):
    def distribution(self):
        return {"dividPlanDate":"2024-01-02","dividRegistDate":"2024-01-03",
                "dividOperateDate":"2024-01-04","dividPayDate":"2024-01-04",
                "dividStockMarketDate":"","dividCashPsBeforeTax":".1","dividStocksPs":"0",
                "dividReserveToStockPs":"","dividCashStock":"10派1元（含税）"}

    def test_missing_economic_fields_require_explicit_cash_only_evidence(self):
        row=self.distribution()
        event=canonical_distributions({"SH600004":{"distributions":[row]}},{})[0]
        self.assertEqual(event.capital_per_share,0)
        for field in ("dividCashPsBeforeTax","dividStocksPs"):
            changed={**row,field:""}
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"missing distribution"):
                canonical_distributions({"SH600004":{"distributions":[changed]}},{})
        for text in ("10转1派1元", "", "10送1派1元"):
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,"capital"):
                canonical_distributions({"SH600004":{"distributions":[{**row,"dividCashStock":text}]}},{})

    def test_quarantined_unknown_actions_and_unexplained_reference_changes_block_admission(self):
        rows=[{"date":"2024-01-03","close":"10","preclose":"10"},
              {"date":"2024-01-04","close":"9.9","preclose":"9.9"},
              {"date":"2024-01-05","close":"9.9","preclose":"9.9"}]
        packet={"bars":rows,"distributions":[self.distribution()],"quarantine":[],
                "adjustments":[{"dividOperateDate":"2024-01-05"}]}
        # Vendor adjustment factor may be recorded one session after the actual ex date.
        validate_source_coverage({"SH600004":packet})
        changed=copy.deepcopy(packet);changed["quarantine"]=[{"reason":"MISSING_OPERATE_DATE","record":{}}]
        with self.assertRaisesRegex(ValueError,"quarantin"):
            validate_source_coverage({"SH600004":changed})
        changed=copy.deepcopy(packet);changed["distributions"]=[]
        with self.assertRaisesRegex(ValueError,"reference|adjustment"):
            validate_source_coverage({"SH600004":changed})
        changed=copy.deepcopy(packet);changed["adjustments"]=[{"dividOperateDate":"2024-01-03"}]
        with self.assertRaisesRegex(ValueError,"adjustment"):
            validate_source_coverage({"SH600004":changed})

    def test_suspended_missing_open_does_not_abort_and_impossible_volume_invalidates_case(self):
        calendar=TradingCalendar(["2023-12-29","2024-01-02"])
        row={"date":"2023-12-29","open":"10","close":"10","preclose":"10",
             "volume":"1000000","tradestatus":"1","isST":"0"}
        bars={"SH600004":{"2023-12-29":row,"2024-01-02":{**row,"date":"2024-01-02","volume":"1"}}}
        targets={"2024-01-02":{"as_of":"2023-12-29","weights":{"SH600004":.95}}}
        case=simulate_fixed_targets(calendar,bars,(),targets,"100000")
        self.assertEqual(case["execution_status"],"INVALID_OBSERVED_TAPE_CAPACITY")
        self.assertEqual(case["whole_day_volume_violations"],1)
        self.assertEqual(case["fills"][0]["quantity"],9500) # diagnostic retained, never resized from future volume
        bars["SH600004"]["2024-01-02"].update(tradestatus="0",open="",close="")
        case=simulate_fixed_targets(calendar,bars,(),targets,"100000")
        self.assertEqual(case["fills"],[])
        self.assertEqual(case["orders"][0]["status"],"UNFILLED_MARKET_CONSTRAINT")
        self.assertEqual(case["days"][-1]["equity"],Decimal("100000"))
