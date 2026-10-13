import copy
from dataclasses import replace
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from stock_rsi.data import Dataset, digest
from stock_rsi.factors import FactorFrame
from stock_rsi.policy import PolicyBundle
from stock_rsi.portfolio import PortfolioProposal, account_hash, keep_current_proposal
from stock_rsi.portfolio_runner import replay_portfolio, run_portfolio
from stock_rsi.time import parse_time


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/fixtures/synthetic_cn_v1.json"
BUNDLE = ROOT / "policies/v0.2-contract-fixture"


class EmptyFactors:
    version = "empty-factors-v1"

    def build(self, snapshot, wake, account):
        return FactorFrame.from_evidence(snapshot, [])


class LiteralPolicy:
    def __init__(self):
        self.bundle = PolicyBundle.load(BUNDLE)
        self.bundle_id = self.bundle.bundle_id

    def propose(self, snapshot, wake, account, factors):
        records = [row for row in snapshot.to_dict()["records"] if row["kind"] == "bar"]
        evidence = [records[-1]["record_id"]]
        expiry = parse_time(snapshot.to_dict()["as_of"]) + timedelta(days=1)
        keep = keep_current_proposal(snapshot, account, self.bundle_id, evidence, expiry)
        alternative = PortfolioProposal.from_dict({
            "schema_version": "portfolio-proposal-v1",
            "proposal_id": "literal-half-risk",
            "policy_bundle_id": self.bundle_id,
            "snapshot_hash": snapshot.sha256,
            "account_hash": account_hash(account),
            "targets": [
                {"security_id": "CASH", "weight": "0.500000"},
                {"security_id": "SYN_A", "weight": "0.500000"},
            ],
            "horizon_sessions": 5,
            "expires_at": expiry.isoformat(),
            "evidence_ids": evidence,
            "rationale": "literal integration candidate",
            "constraints": {"long_only": True},
            "construction": {"source": "test"},
        }, snapshot, account, {"SYN_A"}, self.bundle_id)
        return keep, alternative


class LiteralSelector:
    version = "literal-selector-v1"

    def select(self, snapshot, account, proposals):
        return "literal-half-risk"


class KeepAfterFirstSelector:
    version = "keep-after-first-v1"

    def __init__(self):
        self.calls = 0

    def select(self, snapshot, account, proposals):
        self.calls += 1
        return "literal-half-risk" if self.calls == 1 else "keep-current"


class FailingSelector:
    version = "failing-selector-v1"

    def select(self, snapshot, account, proposals):
        raise ValueError("selector crashed")


class PortfolioRunnerTests(unittest.TestCase):
    def config(self):
        return {
            "start": "2024-09-02T17:00:00+08:00",
            "end": "2024-09-03T16:00:00+08:00",
            "initial_cash": "10000",
            "cost_bps": "20",
        }

    def test_portfolio_run_records_all_candidates_before_selection_and_rebalances(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            report = run_portfolio(DATA, self.config(), LiteralPolicy(), LiteralSelector(), EmptyFactors(), output)
            self.assertEqual(report["status"], "COMPLETED_ENGINEERING")
            self.assertEqual(len(report["candidate_sets"]), 2)
            self.assertEqual(len(report["selections"]), 2)
            known = {row["candidate_set_hash"] for row in report["candidate_sets"]}
            self.assertTrue(all(row["candidate_set_hash"] in known for row in report["selections"]))
            self.assertTrue(all(len(row["candidates"]) == 2 for row in report["candidate_sets"]))
            self.assertTrue(all("outcome" not in candidate for row in report["candidate_sets"] for candidate in row["candidates"]))
            self.assertEqual([(row["action"], row["security_id"], row["quantity"]) for row in report["fills"]], [("BUY", "SYN_A", 500)])
            self.assertEqual(report["account"]["cash"], "4990.00")
            self.assertEqual(report["account"]["positions"]["SYN_A"]["quantity"], 500)
            self.assertEqual(report["account"]["equity"], "10040.00")
            with self.assertRaises(FileExistsError):
                run_portfolio(DATA, self.config(), LiteralPolicy(), LiteralSelector(), EmptyFactors(), output)

    def test_portfolio_replay_rejects_candidate_selection_bundle_and_order_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            original = run_portfolio(DATA, self.config(), LiteralPolicy(), LiteralSelector(), EmptyFactors(), source)
            replayed = replay_portfolio(source, root / "replay")
            self.assertEqual(replayed["fills"], original["fills"])
            self.assertEqual(replayed["account"], original["account"])

            for name, mutate in (
                ("candidate", lambda cassette, report, bundle: cassette[0]["candidates"][1].update({"rationale": "tampered"})),
                ("selection", lambda cassette, report, bundle: cassette[0].update({"selected_id": "keep-current"})),
                ("bundle", lambda cassette, report, bundle: bundle.update({"bundle_id": "0" * 64})),
                ("orders", lambda cassette, report, bundle: report["orders"].reverse()),
            ):
                with self.subTest(name=name):
                    target = root / name
                    target.mkdir()
                    for path in source.rglob("*"):
                        if path.is_file():
                            destination = target / path.relative_to(source)
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            destination.write_bytes(path.read_bytes())
                    cassette = json.loads((target / "cassette.json").read_text())
                    report = json.loads((target / "report.json").read_text())
                    bundle = json.loads((target / "policy_bundle.json").read_text())
                    mutate(cassette, report, bundle)
                    (target / "cassette.json").write_text(json.dumps(cassette))
                    (target / "report.json").write_text(json.dumps(report))
                    (target / "policy_bundle.json").write_text(json.dumps(bundle))
                    with self.assertRaises(ValueError):
                        replay_portfolio(target, root / (name + "-replay"))

    def test_future_price_perturbation_preserves_earlier_candidate_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = run_portfolio(DATA, self.config(), LiteralPolicy(), LiteralSelector(), EmptyFactors(), root / "first")
            payload = json.loads(DATA.read_text())
            for row in payload["records"]:
                if row["kind"] == "bar" and row["payload"]["trade_date"] > "2024-09-02":
                    row["payload"]["close"] = row["payload"]["close"] * 3
            changed = root / "changed.json"
            changed.write_text(json.dumps(payload))
            second = run_portfolio(changed, self.config(), LiteralPolicy(), LiteralSelector(), EmptyFactors(), root / "second")
            self.assertEqual(first["candidate_sets"][0]["candidate_set_hash"], second["candidate_sets"][0]["candidate_set_hash"])

    def test_latest_complete_target_cancels_obsolete_pending_orders(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run_portfolio(DATA, self.config(), LiteralPolicy(), KeepAfterFirstSelector(), EmptyFactors(), Path(directory) / "run")
            self.assertEqual(report["fills"], [])
            self.assertEqual(report["account"]["positions"], {})
            self.assertIn("CANCELLED_BY_PORTFOLIO_REPLACEMENT", {row["status"] for row in report["orders"]})

    def test_proposal_expiring_before_eligible_open_cannot_fill(self):
        class ShortExpiryPolicy(LiteralPolicy):
            def propose(self, snapshot, wake, account, factors):
                rows = super().propose(snapshot, wake, account, factors)
                expiry = parse_time(snapshot.to_dict()["as_of"]) + timedelta(minutes=1)
                visible = {row["security_id"] for row in snapshot.to_dict()["records"]}
                output = []
                for row in rows:
                    payload = row.to_dict()
                    payload["expires_at"] = expiry.isoformat()
                    output.append(PortfolioProposal.from_dict(payload, snapshot, account, visible, self.bundle_id))
                return tuple(output)

        with tempfile.TemporaryDirectory() as directory:
            report = run_portfolio(DATA, self.config(), ShortExpiryPolicy(), LiteralSelector(), EmptyFactors(), Path(directory) / "run")
            self.assertEqual(report["fills"], [])
            self.assertEqual({row["status"] for row in report["orders"]}, {"EXPIRED_BEFORE_EXECUTION"})

    def test_runner_revalidates_dataclass_and_keep_current_semantics(self):
        class InvalidWeightPolicy(LiteralPolicy):
            def propose(self, snapshot, wake, account, factors):
                keep, alternative = super().propose(snapshot, wake, account, factors)
                invalid = replace(alternative, targets=(
                    replace(alternative.targets[0], weight="0.000000"),
                    replace(alternative.targets[1], weight="2.000000"),
                ))
                return keep, invalid

        class MislabelledKeepPolicy(LiteralPolicy):
            def propose(self, snapshot, wake, account, factors):
                keep, alternative = super().propose(snapshot, wake, account, factors)
                return replace(keep, targets=alternative.targets), alternative

        class InvalidFactors(EmptyFactors):
            version = "invalid-factors-v1"

            def build(self, snapshot, wake, account):
                return replace(super().build(snapshot, wake, account), as_of="1900-01-01T00:00:00+00:00")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, policy, factors in (
                ("weight", InvalidWeightPolicy(), EmptyFactors()),
                ("keep", MislabelledKeepPolicy(), EmptyFactors()),
                ("factors", LiteralPolicy(), InvalidFactors()),
            ):
                report = run_portfolio(DATA, self.config(), policy, LiteralSelector(), factors, root / name)
                self.assertEqual(report["status"], "INVALID_POLICY")
                self.assertEqual(report["fills"], [])

    def test_replay_checks_saved_snapshots_and_complete_regenerated_cassette(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_source = root / "snapshot-source"
            run_portfolio(DATA, self.config(), LiteralPolicy(), LiteralSelector(), EmptyFactors(), snapshot_source)
            first_snapshot = next((snapshot_source / "snapshots").glob("*.json"))
            first_snapshot.write_text("{}")
            with self.assertRaises(ValueError):
                replay_portfolio(snapshot_source, root / "snapshot-replay")

            cassette_source = root / "cassette-source"
            run_portfolio(DATA, self.config(), LiteralPolicy(), LiteralSelector(), EmptyFactors(), cassette_source)
            cassette = json.loads((cassette_source / "cassette.json").read_text())
            cassette[0]["decisions"][0]["quantity"] = 999999
            report = json.loads((cassette_source / "report.json").read_text())
            report["manifest"]["cassette_hash"] = digest(cassette)
            (cassette_source / "cassette.json").write_text(json.dumps(cassette))
            (cassette_source / "report.json").write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                replay_portfolio(cassette_source, root / "cassette-replay")

    def test_selector_failure_preserves_candidates_and_replays_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            report = run_portfolio(DATA, self.config(), LiteralPolicy(), FailingSelector(), EmptyFactors(), source)
            self.assertEqual(report["status"], "INVALID_POLICY")
            self.assertEqual(len(report["candidate_sets"]), 2)
            cassette = json.loads((source / "cassette.json").read_text())
            self.assertTrue(all(row["error_stage"] == "selector" and len(row["candidates"]) == 2 for row in cassette))
            replayed = replay_portfolio(source, root / "replay")
            self.assertEqual(replayed["status"], "INVALID_POLICY")
            self.assertEqual(replayed["candidate_sets"], report["candidate_sets"])

    def test_runner_requires_complete_policy_bundle_artifact(self):
        inner = LiteralPolicy()

        class IdOnlyPolicy:
            bundle_id = inner.bundle_id

            def propose(self, snapshot, wake, account, factors):
                return inner.propose(snapshot, wake, account, factors)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            with self.assertRaises(ValueError):
                run_portfolio(DATA, self.config(), IdOnlyPolicy(), LiteralSelector(), EmptyFactors(), output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
