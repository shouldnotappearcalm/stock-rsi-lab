import copy
import unittest
from datetime import timedelta
from pathlib import Path

from stock_rsi.data import Dataset
from stock_rsi.portfolio import (
    PortfolioProposal,
    TargetWeight,
    account_hash,
    keep_current_proposal,
)
from stock_rsi.time import parse_time


DATA = Path(__file__).resolve().parents[1] / "data/fixtures/synthetic_cn_v1.json"
POLICY_ID = "a" * 64


class PortfolioProposalTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = Dataset.load(DATA).snapshot(parse_time("2024-09-30T17:00:00+08:00"))
        self.visible_id = self.snapshot.to_dict()["records"][-1]["record_id"]
        self.account = {
            "cash": "4000.00",
            "positions": {
                "SYN_A": {
                    "quantity": 600,
                    "average_price": "9.50",
                    "mark_price": "10.00",
                    "mark_source": "VISIBLE_PRICE",
                    "mark_trade_date": "2024-09-30",
                    "holding_sessions": 2,
                }
            },
            "market_value": "6000.00",
            "equity": "10000.00",
            "pending_orders": [],
        }
        self.expiry = parse_time(self.snapshot.to_dict()["as_of"]) + timedelta(days=1)

    def payload(self, **changes):
        payload = {
            "schema_version": "portfolio-proposal-v1",
            "proposal_id": "risk-on-a",
            "policy_bundle_id": POLICY_ID,
            "snapshot_hash": self.snapshot.sha256,
            "account_hash": account_hash(self.account),
            "targets": [
                {"security_id": "SYN_A", "weight": "0.600000"},
                {"security_id": "CASH", "weight": "0.400000"},
            ],
            "horizon_sessions": 20,
            "expires_at": self.expiry.isoformat(),
            "evidence_ids": [self.visible_id],
            "rationale": "literal target for contract verification",
            "constraints": {"long_only": True},
            "construction": {"tie_break": "security_id"},
        }
        payload.update(changes)
        return payload

    def proposal(self, payload=None, **bindings):
        return PortfolioProposal.from_dict(
            payload or self.payload(),
            bindings.get("snapshot", self.snapshot),
            bindings.get("account", self.account),
            bindings.get("eligible", {"SYN_A"}),
            bindings.get("policy_bundle_id", POLICY_ID),
        )

    def test_proposal_is_bound_to_snapshot_account_policy_and_complete_weights(self):
        proposal = self.proposal()
        self.assertEqual([row["weight"] for row in proposal.to_dict()["targets"]], ["0.400000", "0.600000"])
        self.assertEqual(proposal.to_dict()["snapshot_hash"], self.snapshot.sha256)
        self.assertEqual(proposal.to_dict()["account_hash"], account_hash(self.account))
        reversed_payload = self.payload(targets=list(reversed(self.payload()["targets"])))
        self.assertEqual(self.proposal(reversed_payload).sha256, proposal.sha256)
        changed_account = copy.deepcopy(self.account)
        changed_account["cash"] = "3999.00"
        self.assertNotEqual(account_hash(changed_account), account_hash(self.account))

    def test_target_weight_rejects_noncanonical_decimals(self):
        invalid = [True, 1, "1e-1", "0.1", "0.1000000", "-0.100000", "1.000001"]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                TargetWeight.from_dict({"security_id": "SYN_A", "weight": value})

    def test_proposal_rejects_invalid_targets_and_identity_reuse(self):
        scenarios = [
            self.payload(targets=[{"security_id": "CASH", "weight": "0.400000"}, {"security_id": "CASH", "weight": "0.600000"}]),
            self.payload(targets=[{"security_id": "SYN_A", "weight": "1.000000"}]),
            self.payload(targets=[{"security_id": "SYN_A", "weight": "0.600000"}, {"security_id": "SYN_B", "weight": "0.100000"}, {"security_id": "CASH", "weight": "0.300000"}]),
            self.payload(targets=[{"security_id": "SYN_A", "weight": "0.600000"}, {"security_id": "CASH", "weight": "0.399999"}]),
            self.payload(evidence_ids=["future-record"]),
            self.payload(snapshot_hash="b" * 64),
            self.payload(account_hash="b" * 64),
            self.payload(policy_bundle_id="b" * 64),
        ]
        for payload in scenarios:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.proposal(payload)

    def test_keep_current_proposal_conserves_weights_and_rejects_bad_marks(self):
        proposal = keep_current_proposal(
            self.snapshot, self.account, POLICY_ID, [self.visible_id], self.expiry,
        )
        self.assertEqual(proposal.proposal_id, "keep-current")
        self.assertEqual(proposal.to_dict()["targets"], [
            {"security_id": "CASH", "weight": "0.400000"},
            {"security_id": "SYN_A", "weight": "0.600000"},
        ])
        bad = copy.deepcopy(self.account)
        bad["positions"]["SYN_A"]["mark_source"] = "COST_UNMARKED"
        with self.assertRaises(ValueError):
            keep_current_proposal(self.snapshot, bad, POLICY_ID, [self.visible_id], self.expiry)

    def test_keep_current_uses_deterministic_largest_remainder_rounding(self):
        account = {
            "cash": "1",
            "positions": {
                "SYN_A": {"quantity": 1, "mark_price": "1", "mark_source": "VISIBLE_PRICE"},
                "SYN_B": {"quantity": 1, "mark_price": "1", "mark_source": "VISIBLE_PRICE"},
            },
            "market_value": "2",
            "equity": "3",
            "pending_orders": [],
        }
        proposal = keep_current_proposal(
            self.snapshot, account, POLICY_ID, [self.visible_id], self.expiry,
        )
        self.assertEqual(proposal.to_dict()["targets"], [
            {"security_id": "CASH", "weight": "0.333334"},
            {"security_id": "SYN_A", "weight": "0.333333"},
            {"security_id": "SYN_B", "weight": "0.333333"},
        ])
        bad = copy.deepcopy(self.account)
        bad["equity"] = "10001.00"
        with self.assertRaises(ValueError):
            keep_current_proposal(self.snapshot, bad, POLICY_ID, [self.visible_id], self.expiry)


if __name__ == "__main__":
    unittest.main()
