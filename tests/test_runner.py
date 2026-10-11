import json
import tempfile
import unittest
from pathlib import Path

from stock_rsi.data import Dataset
from stock_rsi.models import Decision
try:
    from stock_rsi.runner import run, replay
    from stock_rsi.skill import Skill, RuleAgent
except ImportError:
    run = replay = Skill = RuleAgent = None

DATA = Path(__file__).resolve().parents[1] / "data/fixtures/synthetic_cn_v1.json"


class ScriptedAgent:
    version = "literal-script-v1"

    def decide(self, snapshot, wake, account):
        at = snapshot.to_dict()["as_of"]
        ids = [row["record_id"] for row in snapshot.to_dict()["records"]]
        if at == "2024-09-30T09:00:00+00:00":
            action, quantity = "BUY", 100
        elif at == "2024-10-08T09:00:00+00:00":
            action, quantity = "SELL", 100
        else:
            action, quantity = "HOLD", 0
        return Decision.from_dict({"action": action, "security_id": "SYN_A", "quantity": quantity,
                                  "evidence_ids": ids[-1:], "reason": "literal timeline"}, snapshot)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(run, "runner/skill implementation missing")

    def config(self):
        return {"start": "2024-09-30T00:00:00+08:00", "end": "2024-10-09T23:00:00+08:00", "initial_cash": "2000", "cost_bps": "20"}

    def test_agent_trade_replays_across_holiday_with_hand_checked_cash(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run(DATA, self.config(), ScriptedAgent(), Path(directory)/"first")
            self.assertEqual([fill["execution_at"] for fill in report["fills"]], ["2024-10-08T01:30:00+00:00", "2024-10-09T01:30:00+00:00"])
            # buy 100*11.7 +2.34, sell 100*12.98 -2.60
            self.assertEqual(report["account"]["cash"], "2123.06")
            self.assertEqual(report["account"]["positions"], {})
            self.assertEqual(report["manifest"]["evidence_level"], "SYNTHETIC_REGRESSION")
            replayed = replay(Path(directory)/"first", Path(directory)/"again")
            self.assertEqual(replayed["fills"], report["fills"])
            self.assertEqual(replayed["account"], report["account"])

    def test_replay_rejects_tampered_response_and_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory)/"first"
            run(DATA, self.config(), ScriptedAgent(), first)
            cassette = json.loads((first/"cassette.json").read_text())
            cassette[0]["decision"]["reason"] = "tampered"
            (first/"cassette.json").write_text(json.dumps(cassette))
            with self.assertRaises(ValueError):
                replay(first, Path(directory)/"again")

    def test_errors_are_recorded_and_not_silently_counted_as_valid(self):
        class Broken:
            version = "broken"
            def decide(self, *_):
                raise RuntimeError("fixture failure")
        with tempfile.TemporaryDirectory() as directory:
            report = run(DATA, self.config(), Broken(), Path(directory)/"run")
            self.assertEqual(report["status"], "INVALID_AGENT")
            self.assertGreater(len(report["errors"]), 0)
            self.assertEqual(report["fills"], [])

    def test_snapshot_from_future_price_cannot_change_earlier_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            first = run(DATA, self.config(), ScriptedAgent(), Path(directory)/"first")
            payload = json.loads(DATA.read_text())
            for record in payload["records"]:
                if record["available_at"] >= "2024-10-08":
                    if record["kind"] == "filing":
                        record["payload"]["profit"] = -9999
            changed = Path(directory)/"changed.json"
            changed.write_text(json.dumps(payload))
            second = run(changed, self.config(), ScriptedAgent(), Path(directory)/"second")
            old = next(row for row in first["wakes"] if row["at"] == "2024-09-30T09:00:00+00:00")
            new = next(row for row in second["wakes"] if row["at"] == "2024-09-30T09:00:00+00:00")
            self.assertEqual(old["snapshot_hash"], new["snapshot_hash"])
            self.assertEqual(old["decision"], new["decision"])

    def test_replay_output_directory_cannot_overwrite_original(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory)/"first"
            run(DATA, self.config(), ScriptedAgent(), first)
            with self.assertRaises(FileExistsError):
                replay(first, first)

    def test_skill_rejects_unbounded_patch_and_deterministic_agent_uses_snapshot(self):
        skill = Skill.from_dict({"trend_window": 10, "pullback_window": 3, "min_pullback": 0.01, "max_pullback": 0.08, "target_weight": 0.10, "max_holding_sessions": 5})
        with self.assertRaises(ValueError):
            skill.patch({"target_weight": 2})
        with self.assertRaises(ValueError):
            skill.patch({"cost_bps": 0})
        data = Dataset.load(DATA)
        snap = data.snapshot(__import__('stock_rsi.time',fromlist=['parse_time']).parse_time("2024-09-30T17:00:00+08:00"))
        agent = RuleAgent(skill)
        from stock_rsi.scheduler import Wake
        from stock_rsi.time import parse_time
        result = agent.decide(snap, Wake(parse_time("2024-09-30T17:00:00+08:00"),("WEEKLY_REVIEW",)), {"cash":"20000","positions":{},"equity":"20000"})
        self.assertEqual(result.action, "BUY")
        self.assertEqual(result.quantity, 100)


if __name__ == '__main__':
    unittest.main()
