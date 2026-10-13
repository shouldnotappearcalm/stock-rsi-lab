import unittest
from pathlib import Path

from stock_rsi.data import Dataset
from stock_rsi.factors import FactorEvidence, FactorFrame
from stock_rsi.time import parse_time


DATA = Path(__file__).resolve().parents[1] / "data/fixtures/synthetic_cn_v1.json"


class FactorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = Dataset.load(DATA).snapshot(parse_time("2024-09-30T17:00:00+08:00"))
        self.as_of = self.snapshot.to_dict()["as_of"]
        self.visible_id = self.snapshot.to_dict()["records"][-1]["record_id"]

    def payload(self, **changes):
        payload = {
            "factor_id": "price.momentum_20",
            "security_id": "SYN_A",
            "value": 0.125,
            "unit": "ratio",
            "as_of": self.as_of,
            "lookback_sessions": 20,
            "evidence_ids": [self.visible_id],
            "quality_flags": ["SYNTHETIC"],
            "missing_reason": None,
        }
        payload.update(changes)
        return payload

    def test_factor_evidence_is_snapshot_bound_and_round_trips(self):
        factor = FactorEvidence.from_dict(self.payload(), self.snapshot)
        self.assertEqual(factor.to_dict(), {
            "factor_id": "price.momentum_20",
            "security_id": "SYN_A",
            "value": "0.125",
            "unit": "ratio",
            "as_of": self.as_of,
            "lookback_sessions": 20,
            "evidence_ids": [self.visible_id],
            "quality_flags": ["SYNTHETIC"],
            "missing_reason": None,
            "snapshot_hash": self.snapshot.sha256,
        })

    def test_factor_evidence_rejects_malformed_or_invisible_values(self):
        scenarios = [
            {"value": True},
            {"value": float("nan")},
            {"value": float("inf")},
            {"evidence_ids": ["future-record"]},
            {"as_of": "2024-09-30T16:59:59+08:00"},
            {"unit": ""},
            {"value": 1, "missing_reason": "also missing"},
            {"value": None, "missing_reason": None},
        ]
        for changes in scenarios:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                FactorEvidence.from_dict(self.payload(**changes), self.snapshot)

    def test_missing_factor_requires_reason_and_allows_zero_lookback(self):
        factor = FactorEvidence.from_dict(self.payload(
            factor_id="identity.board",
            value=None,
            missing_reason="historical board unavailable",
            lookback_sessions=0,
        ), self.snapshot)
        self.assertIsNone(factor.to_dict()["value"])
        self.assertEqual(factor.to_dict()["missing_reason"], "historical board unavailable")

    def test_factor_frame_rejects_duplicates_and_cross_snapshot_evidence(self):
        first = FactorEvidence.from_dict(self.payload(), self.snapshot)
        second = FactorEvidence.from_dict(self.payload(
            factor_id="risk.volatility_20",
            value="0.2",
        ), self.snapshot)
        frame = FactorFrame.from_evidence(self.snapshot, [second, first])
        reversed_frame = FactorFrame.from_evidence(self.snapshot, [first, second])
        self.assertEqual(frame.sha256, reversed_frame.sha256)
        self.assertEqual(frame.get("price.momentum_20", "SYN_A"), first)
        with self.assertRaises(KeyError):
            frame.get("missing", "SYN_A")
        with self.assertRaises(ValueError):
            FactorFrame.from_evidence(self.snapshot, [first, first])

        later = Dataset.load(DATA).snapshot(parse_time("2024-10-08T17:00:00+08:00"))
        with self.assertRaises(ValueError):
            FactorFrame.from_evidence(later, [first])


if __name__ == "__main__":
    unittest.main()
