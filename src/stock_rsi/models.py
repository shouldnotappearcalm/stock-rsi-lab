from dataclasses import dataclass

from .data import Snapshot, digest


@dataclass(frozen=True)
class Decision:
    action: str
    security_id: str
    quantity: int
    evidence_ids: tuple[str, ...]
    reason: str
    snapshot_hash: str

    @classmethod
    def from_dict(cls, data, snapshot: Snapshot):
        keys = {"action", "security_id", "quantity", "evidence_ids", "reason"}
        if not isinstance(data, dict) or set(data) != keys:
            raise ValueError("decision fields do not match schema")
        action, quantity = data["action"], data["quantity"]
        if action not in ("BUY", "SELL", "HOLD", "ABSTAIN"):
            raise ValueError("invalid action")
        if type(quantity) is not int or quantity < 0:
            raise ValueError("quantity must be a nonnegative integer")
        if (action in ("BUY", "SELL")) != (quantity > 0):
            raise ValueError("quantity/action mismatch")
        if not isinstance(data["security_id"], str) or not data["security_id"]:
            raise ValueError("security_id required")
        evidence = data["evidence_ids"]
        if not isinstance(evidence, list) or not all(isinstance(x, str) for x in evidence):
            raise ValueError("evidence IDs must be a list of strings")
        visible = {row["record_id"] for row in snapshot.to_dict()["records"]}
        if not set(evidence) <= visible:
            raise ValueError("invisible evidence")
        if action in ("BUY", "SELL") and not evidence:
            raise ValueError("trade requires visible evidence")
        if not isinstance(data["reason"], str) or not data["reason"].strip():
            raise ValueError("reason required")
        return cls(action, data["security_id"], quantity, tuple(evidence), data["reason"], snapshot.sha256)

    def to_dict(self):
        return {"action": self.action, "security_id": self.security_id, "quantity": self.quantity,
                "evidence_ids": list(self.evidence_ids), "reason": self.reason}

    @property
    def decision_id(self):
        return digest({"decision": self.to_dict(), "snapshot": self.snapshot_hash})
