import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .data import digest
from .models import Decision


@dataclass(frozen=True)
class Skill:
    trend_window: int = 10
    pullback_window: int = 3
    min_pullback: float = 0.01
    max_pullback: float = 0.08
    target_weight: float = 0.10
    max_holding_sessions: int = 5

    @classmethod
    def from_dict(cls, data):
        if set(data) != set(cls.__dataclass_fields__):
            raise ValueError("unknown or missing skill fields")
        for key, lo, hi in (("trend_window", 3, 120), ("pullback_window", 1, 20), ("max_holding_sessions", 1, 20)):
            if type(data[key]) is not int or not lo <= data[key] <= hi:
                raise ValueError(f"invalid {key}")
        for key in ("min_pullback", "max_pullback", "target_weight"):
            value = data[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"finite {key} required")
        if not 0 <= data["min_pullback"] < data["max_pullback"] <= .30 or not 0 < data["target_weight"] <= .10:
            raise ValueError("skill outside allowed search space")
        if data["pullback_window"] >= data["trend_window"]:
            raise ValueError("pullback window must be shorter than trend window")
        return cls(**data)

    def to_dict(self):
        return asdict(self)

    @property
    def sha256(self):
        return digest(self.to_dict())

    def patch(self, patch):
        if not isinstance(patch, dict) or not patch or not set(patch) <= set(self.to_dict()):
            raise ValueError("invalid skill patch")
        return Skill.from_dict(self.to_dict() | patch)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))


class RuleAgent:
    def __init__(self, skill: Skill):
        self.skill = skill
        self.version = "rule-v1:" + skill.sha256

    def decide(self, snapshot, wake, account):
        visible = snapshot.to_dict()["records"]
        groups = {}
        for row in visible:
            if row["kind"] == "bar":
                groups.setdefault(row["security_id"], []).append(row)
        action, quantity, evidence, reason = "HOLD", 0, [], "no applicable signal"
        security = next(iter(sorted(groups)), "NO_SECURITY")
        for security, records in sorted(groups.items()):
            records = sorted(records, key=lambda row: row["payload"]["trade_date"])
            bars = [row for row in records if not row["payload"].get("suspended", False)]
            position = account["positions"].get(security)
            if position and position.get("holding_sessions", 0) >= self.skill.max_holding_sessions:
                action, quantity, reason = "SELL", position["quantity"], "holding horizon reached"
                evidence = [records[-1]["record_id"]]
                break
            if len(bars) < self.skill.trend_window:
                continue
            sample = bars[-self.skill.trend_window:]
            closes = [float(row["payload"]["close"]) for row in sample]
            current = closes[-1]
            trend = current / closes[0] - 1
            pullback = 1 - current / max(closes[-self.skill.pullback_window:])
            if position:
                if trend <= 0:
                    action, quantity, reason = "SELL", position["quantity"], "trend invalidated"
                    evidence = [row["record_id"] for row in sample]
                    break
                continue
            is_research_wake = "WEEKLY_REVIEW" in wake.reasons or any(r.startswith("ARRIVAL:") for r in wake.reasons)
            if is_research_wake and trend > 0 and self.skill.min_pullback <= pullback <= self.skill.max_pullback:
                quantity = int(float(account["equity"]) * self.skill.target_weight / current) // 100 * 100
                if quantity:
                    action, reason = "BUY", "uptrend with bounded pullback"
                    evidence = [row["record_id"] for row in sample]
                    break
        return Decision.from_dict({"action": action, "security_id": security, "quantity": quantity,
                                   "evidence_ids": evidence, "reason": reason}, snapshot)
