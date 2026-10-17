import copy
import json
import tempfile
import unittest
from decimal import Decimal
from functools import partial
from pathlib import Path

from scripts.run_low_risk_raw_share_validation import simulate_fixed_targets
from scripts.run_low_risk_feedback_cost_stress import profile_factory, require_zero_controls, main as feedback_main
from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import Snapshot, canonical
from stock_rsi.execution_cost import ExecutionCostBroker, SingleOrderLimitError
from stock_rsi.models import Decision
from stock_rsi.raw_share_account import RawShareAccount
from stock_rsi.time import parse_time


def decision(action, quantity, code="SYN_A"):
    snapshot=Snapshot(canonical({"as_of":"2024-01-01T00:00:00+00:00","records":[{"record_id":"e"}]}))
    return Decision.from_dict({"action":action,"security_id":code,"quantity":quantity,
                               "evidence_ids":["e"],"reason":"literal cost fixture"},snapshot)


def factory(bps):
    return partial(RawShareAccount,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps))


class ExecutionCostFeedbackTests(unittest.TestCase):
    def test_extra_cost_is_added_after_minimum_fee_and_changes_affordable_lot(self):
        calendar=TradingCalendar(["2024-01-02","2024-01-03"])
        base=ExecutionCostBroker(calendar,"1005",extra_cost_bps=0,buy_cost_bps="5",min_cost="5")
        costly=ExecutionCostBroker(calendar,"1005",extra_cost_bps=20,buy_cost_bps="5",min_cost="5")
        at=parse_time("2024-01-02T15:05:00+08:00")
        for broker in (base,costly):broker.submit(decision("BUY",100),at)
        bar={"security_id":"SYN_A","trade_date":"2024-01-03","open":"10","suspended":False,
             "limit_up":"11","limit_down":"9"}
        self.assertEqual(base.on_open(bar)[0]["cost"],"5.00")
        self.assertEqual(base.cash,Decimal(0))
        self.assertEqual(costly.on_open(bar),[])
        self.assertEqual(costly.cash,Decimal("1005"))
        self.assertEqual(costly._cost(Decimal("1000"),"BUY"),Decimal("7.00"))
        for value in (True,-1,1.5,float('inf')):
            with self.assertRaises(ValueError):ExecutionCostBroker(calendar,extra_cost_bps=value)

    def test_oversized_batch_fails_before_cancelling_existing_intent(self):
        calendar=TradingCalendar(["2024-01-02","2024-01-03"])
        broker=ExecutionCostBroker(calendar,"2000")
        at=parse_time("2024-01-02T15:05:00+08:00")
        broker.submit(decision("BUY",100),at)
        before=copy.deepcopy(broker.orders)
        with self.assertRaises(SingleOrderLimitError):
            broker.replace_pending_intent([decision("BUY",100,"SYN_B"),decision("SELL",1000001)],
                                          at,calendar.at(calendar.days[1],"09:30:00"))
        self.assertEqual(broker.orders,before)
        self.assertEqual(broker.fills,[])
        with self.assertRaisesRegex(ValueError,"100-share"):
            broker.replace_pending_intent([decision("BUY",100,"SYN_B"),decision("BUY",101)],
                                          at,calendar.at(calendar.days[1],"09:30:00"))
        self.assertEqual(broker.orders,before)
        with self.assertRaises(ValueError):broker.replace_pending_intent([{}],at,calendar.at(calendar.days[1],"09:30:00"))
        self.assertEqual(broker.orders,before)

    def test_unregistered_cost_and_changed_plan_cannot_start_campaign(self):
        for value in (True,1,50,-1):
            with self.assertRaises(ValueError):profile_factory(value)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);plan=root/'plan.json';plan.write_text(json.dumps({"status":"changed"}))
            output=root/'never-created'
            with self.assertRaisesRegex(ValueError,"plan changed"):
                feedback_main(['--data-dir',str(root/'data'),'--proof-dir',str(root/'proof'),
                               '--targets',str(root/'targets'),'--parent-replay-dir',str(root/'parent'),
                               '--plan',str(plan),'--expected-plan-sha256','0'*64,'--output-dir',str(output)])
            self.assertFalse(output.exists())

    def test_all_zero_cost_controls_must_pass_before_positive_cost_profiles(self):
        controls={capital:"BYTE_EXACT_PARENT_REPRODUCED" for capital in ("100000","1000000","10000000")}
        controls["100000000"]="REJECTED_KNOWN_OVERSIZED_PARENT_NOT_RETROACTIVELY_SPLIT"
        require_zero_controls(controls)
        for capital in controls:
            changed={**controls,capital:"INVALID"}
            with self.subTest(capital=capital),self.assertRaises(RuntimeError):require_zero_controls(changed)

    def test_feedback_resizes_later_orders_and_future_prices_do_not_change_past(self):
        days=["2023-12-29","2024-01-02","2024-01-31","2024-02-01"]
        calendar=TradingCalendar(days)
        def row(day):return {"date":day,"open":"1","close":"1","preclose":"1",
                             "volume":"10000000","tradestatus":"1","isST":"0"}
        bars={"SYN_A":{day:row(day) for day in days}}
        targets={"2024-01-02":{"as_of":"2023-12-29","weights":{"SYN_A":".95"}},
                 "2024-02-01":{"as_of":"2024-01-31","weights":{"SYN_A":".95"}}}
        baseline=simulate_fixed_targets(calendar,bars,(),targets,"50000")
        zero=simulate_fixed_targets(calendar,bars,(),targets,"50000",account_factory=factory(0))
        stressed=simulate_fixed_targets(calendar,bars,(),targets,"50000",account_factory=factory(40))
        self.assertEqual(baseline,zero)
        self.assertEqual(baseline["intents"][0],stressed["intents"][0])
        self.assertEqual(baseline["intents"][1]["decisions"][0]["quantity"],100)
        self.assertEqual(stressed["intents"][1]["decisions"][0]["quantity"],300)
        self.assertNotEqual(baseline["intents"][1]["snapshot_sha256"],stressed["intents"][1]["snapshot_sha256"])
        self.assertLess(stressed["days"][-1]["equity"],baseline["days"][-1]["equity"])
        changed=copy.deepcopy(bars);changed["SYN_A"]["2024-02-01"].update(open="1.01",close="2")
        later=simulate_fixed_targets(calendar,changed,(),targets,"50000",account_factory=factory(40))
        self.assertEqual(stressed["intents"],later["intents"])
