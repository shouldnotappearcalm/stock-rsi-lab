import unittest
from datetime import timedelta

from stock_rsi.data import Snapshot, canonical
from stock_rsi.broker import Broker
from stock_rsi.calendar import TradingCalendar
from stock_rsi.models import Decision
from stock_rsi.portfolio import PortfolioProposal, account_hash
from stock_rsi.targeting import plan_target_orders
from stock_rsi.time import parse_time


POLICY_ID = "c" * 64


def decision_snapshot():
    return Snapshot(canonical({
        "dataset_id": "literal-targeting",
        "evidence_level": "SYNTHETIC_REGRESSION",
        "as_of": "2024-09-30T09:00:00+00:00",
        "records": [
            {"record_id": "a-close", "security_id": "SYN_A", "kind": "bar", "payload": {"trade_date": "2024-09-30", "close": 10}},
            {"record_id": "b-close", "security_id": "SYN_B", "kind": "bar", "payload": {"trade_date": "2024-09-30", "close": 10}},
        ],
    }))


def account():
    return {
        "cash": "1000",
        "positions": {"SYN_A": {"quantity": 200, "mark_price": "10", "mark_source": "VISIBLE_PRICE"}},
        "market_value": "2000",
        "equity": "3000",
        "pending_orders": [],
    }


def proposal(snapshot, current_account, evidence_ids=("a-close", "b-close")):
    expiry = parse_time(snapshot.to_dict()["as_of"]) + timedelta(days=1)
    return PortfolioProposal.from_dict({
        "schema_version": "portfolio-proposal-v1",
        "proposal_id": "rotate-a-to-b",
        "policy_bundle_id": POLICY_ID,
        "snapshot_hash": snapshot.sha256,
        "account_hash": account_hash(current_account),
        "targets": [
            {"security_id": "CASH", "weight": "0.400000"},
            {"security_id": "SYN_A", "weight": "0.000000"},
            {"security_id": "SYN_B", "weight": "0.600000"},
        ],
        "horizon_sessions": 5,
        "expires_at": expiry.isoformat(),
        "evidence_ids": list(evidence_ids),
        "rationale": "literal rotation",
        "constraints": {"long_only": True},
        "construction": {"tie_break": "security_id"},
    }, snapshot, current_account, {"SYN_A", "SYN_B"}, POLICY_ID)


class TargetPlannerTests(unittest.TestCase):
    def test_target_planner_emits_exits_before_entries_with_stable_rounding(self):
        snapshot = decision_snapshot()
        current = account()
        decisions = plan_target_orders(proposal(snapshot, current), snapshot, current)
        self.assertEqual([(row.action, row.security_id, row.quantity) for row in decisions], [
            ("SELL", "SYN_A", 200),
            ("BUY", "SYN_B", 100),
        ])
        self.assertTrue(all(row.evidence_ids == ("a-close", "b-close") for row in decisions))
        self.assertTrue(all(row.quantity > 0 for row in decisions))

    def test_target_planner_requires_visible_prices_for_targets_and_reductions(self):
        snapshot = decision_snapshot()
        current = account()
        payload = snapshot.to_dict()
        payload["records"] = [row for row in payload["records"] if row["security_id"] != "SYN_A"]
        missing_held = Snapshot(canonical(payload))
        with self.assertRaises(ValueError):
            plan_target_orders(proposal(missing_held, current, ("b-close",)), missing_held, current)
        payload = snapshot.to_dict()
        payload["records"] = [row for row in payload["records"] if row["security_id"] != "SYN_B"]
        missing_target = Snapshot(canonical(payload))
        with self.assertRaises(ValueError):
            plan_target_orders(proposal(missing_target, current, ("a-close",)), missing_target, current)

    def test_market_open_sells_before_buys_and_marks_missing_bars(self):
        calendar = TradingCalendar(["2024-09-27", "2024-09-30", "2024-10-08", "2024-10-09"])
        snapshot = decision_snapshot()

        def decide(action, security, quantity):
            return Decision.from_dict({
                "action": action,
                "security_id": security,
                "quantity": quantity,
                "evidence_ids": ["a-close"],
                "reason": "literal batch test",
            }, snapshot)

        def bar(security, day):
            return {"security_id": security, "trade_date": day, "open": 10, "close": 10,
                    "limit_up": 11, "limit_down": 9, "suspended": False}

        broker = Broker(calendar, initial_cash="2500", cost_bps="20")
        broker.submit(decide("BUY", "SYN_A", 200), parse_time("2024-09-27T17:00:00+08:00"))
        broker.on_open(bar("SYN_A", "2024-09-30"))
        self.assertEqual(broker.cash, 496)
        broker.submit(decide("SELL", "SYN_A", 200), parse_time("2024-09-30T17:00:00+08:00"))
        broker.submit(decide("BUY", "SYN_B", 200), parse_time("2024-09-30T17:00:00+08:00"))
        fills = broker.on_market_open([bar("SYN_B", "2024-10-08"), bar("SYN_A", "2024-10-08")])
        self.assertEqual([(row["action"], row["security_id"], row["quantity"]) for row in fills], [
            ("SELL", "SYN_A", 200),
            ("BUY", "SYN_B", 200),
        ])
        self.assertEqual(broker.cash, 488)
        self.assertEqual(broker.snapshot()["positions"]["SYN_B"]["quantity"], 200)
        self.assertNotIn("SYN_A", broker.snapshot()["positions"])

        missing = Broker(calendar, initial_cash="5000", cost_bps="20")
        missing.submit(decide("BUY", "SYN_B", 100), parse_time("2024-09-30T17:00:00+08:00"))
        self.assertEqual(missing.on_market_open([bar("SYN_A", "2024-10-08")]), [])
        self.assertEqual(missing.orders[-1]["status"], "INVALID_MISSING_DATA")
        self.assertEqual(missing.cash, 5000)

    def test_market_open_rejects_duplicate_or_mixed_dates_before_mutation(self):
        calendar = TradingCalendar(["2024-09-30", "2024-10-08"])
        broker = Broker(calendar, initial_cash="5000", cost_bps="20")

        def bar(security, day):
            return {"security_id": security, "trade_date": day, "open": 10, "close": 10,
                    "limit_up": 11, "limit_down": 9, "suspended": False}

        for bars in ([bar("SYN_A", "2024-09-30"), bar("SYN_A", "2024-09-30")],
                     [bar("SYN_A", "2024-09-30"), bar("SYN_B", "2024-10-08")]):
            with self.subTest(bars=bars), self.assertRaises(ValueError):
                broker.on_market_open(bars)
            self.assertEqual(broker.cash, 5000)
            self.assertEqual(broker.fills, [])


if __name__ == "__main__":
    unittest.main()
