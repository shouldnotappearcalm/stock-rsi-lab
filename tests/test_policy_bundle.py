import json
import shutil
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from stock_rsi.data import Dataset
from stock_rsi.factors import FactorFrame
from stock_rsi.policy import (
    FactorProvider,
    PolicyBundle,
    PortfolioPolicy,
    ProposalSelector,
    select_proposal,
    validate_candidate_set,
)
from stock_rsi.portfolio import PortfolioProposal, account_hash, keep_current_proposal
from stock_rsi.time import parse_time


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/fixtures/synthetic_cn_v1.json"
FIXTURE = ROOT / "policies/v0.2-contract-fixture"
MODULES = {
    "universe_filter", "regime_policy", "candidate_ranker", "entry_policy",
    "exit_policy", "portfolio_constructor", "execution_policy",
}


class PolicyBundleTests(unittest.TestCase):
    def test_policy_bundle_requires_exact_modules_and_hashes_content(self):
        bundle = PolicyBundle.load(FIXTURE)
        self.assertEqual({bundle.module(name)["module"] for name in MODULES}, MODULES)
        copy = bundle.module("entry_policy")
        copy["parameters"]["changed"] = True
        self.assertEqual(bundle.module("entry_policy")["parameters"], {})

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bundle"
            shutil.copytree(FIXTURE, path)
            original = PolicyBundle.load(path).bundle_id
            payload = json.loads((path / "entry_policy.json").read_text())
            payload["parameters"]["literal"] = 1
            (path / "entry_policy.json").write_text(json.dumps(payload))
            self.assertNotEqual(PolicyBundle.load(path).bundle_id, original)

    def test_policy_bundle_rejects_missing_unknown_parent_and_unsafe_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, mutate in (
                ("missing", lambda data: data["modules"].pop("entry_policy")),
                ("unknown", lambda data: data["modules"].update({"rogue": "rogue.json"})),
                ("parent", lambda data: data.update({"parent_bundle_id": "abc"})),
                ("traversal", lambda data: data["modules"].update({"entry_policy": "../entry_policy.json"})),
            ):
                with self.subTest(name=name):
                    path = root / name
                    shutil.copytree(FIXTURE, path)
                    manifest = json.loads((path / "manifest.json").read_text())
                    mutate(manifest)
                    (path / "manifest.json").write_text(json.dumps(manifest))
                    with self.assertRaises(ValueError):
                        PolicyBundle.load(path)
            symlink = root / "symlink"
            shutil.copytree(FIXTURE, symlink)
            (symlink / "entry_policy.json").unlink()
            (symlink / "entry_policy.json").symlink_to(FIXTURE / "entry_policy.json")
            with self.assertRaises(ValueError):
                PolicyBundle.load(symlink)

    def test_policy_and_selector_protocols_require_multiple_valid_candidates(self):
        bundle = PolicyBundle.load(FIXTURE)
        snapshot = Dataset.load(DATA).snapshot(parse_time("2024-09-30T17:00:00+08:00"))
        visible_id = snapshot.to_dict()["records"][-1]["record_id"]
        account = {"cash": "10000", "positions": {}, "market_value": "0", "equity": "10000", "pending_orders": []}
        expiry = parse_time(snapshot.to_dict()["as_of"]) + timedelta(days=1)
        keep = keep_current_proposal(snapshot, account, bundle.bundle_id, [visible_id], expiry)
        alternative = PortfolioProposal.from_dict({
            "schema_version": "portfolio-proposal-v1",
            "proposal_id": "literal-risk",
            "policy_bundle_id": bundle.bundle_id,
            "snapshot_hash": snapshot.sha256,
            "account_hash": account_hash(account),
            "targets": [
                {"security_id": "CASH", "weight": "0.900000"},
                {"security_id": "SYN_A", "weight": "0.100000"},
            ],
            "horizon_sessions": 5,
            "expires_at": expiry.isoformat(),
            "evidence_ids": [visible_id],
            "rationale": "literal candidate",
            "constraints": {},
            "construction": {"source": "test"},
        }, snapshot, account, {"SYN_A"}, bundle.bundle_id)

        class LiteralFactors:
            version = "literal-factors-v1"

            def build(self, input_snapshot, wake, input_account):
                return FactorFrame.from_evidence(input_snapshot, [])

        class LiteralPolicy:
            bundle_id = bundle.bundle_id

            def propose(self, input_snapshot, wake, input_account, factors):
                return keep, alternative

        class LiteralSelector:
            version = "literal-selector-v1"

            def select(self, input_snapshot, input_account, proposals):
                return "literal-risk"

        policy = LiteralPolicy()
        selector = LiteralSelector()
        self.assertIsInstance(LiteralFactors(), FactorProvider)
        self.assertIsInstance(policy, PortfolioPolicy)
        self.assertIsInstance(selector, ProposalSelector)
        candidates = validate_candidate_set(policy, snapshot, account, (alternative, keep))
        self.assertEqual([row.proposal_id for row in candidates], ["keep-current", "literal-risk"])
        self.assertEqual(select_proposal(selector, snapshot, account, candidates), alternative)
        for bad in ((keep,), (keep, keep), (alternative,)):
            with self.subTest(ids=[row.proposal_id for row in bad]), self.assertRaises(ValueError):
                validate_candidate_set(policy, snapshot, account, bad)

        class UnknownSelector:
            version = "unknown-selector-v1"

            def select(self, input_snapshot, input_account, proposals):
                return "does-not-exist"

        with self.assertRaises(ValueError):
            select_proposal(UnknownSelector(), snapshot, account, candidates)


if __name__ == "__main__":
    unittest.main()
