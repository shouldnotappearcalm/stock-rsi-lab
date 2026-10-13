from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .data import Snapshot, digest
from .time import iso, parse_time


def _nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"nonempty {name} required")
    return value


def _decimal_string(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError("factor value must be numeric")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("factor value must be numeric") from exc
    if not number.is_finite():
        raise ValueError("factor value must be finite")
    return format(number.normalize(), "f")


@dataclass(frozen=True)
class FactorEvidence:
    factor_id: str
    security_id: str
    value: str | None
    unit: str
    as_of: str
    lookback_sessions: int
    evidence_ids: tuple[str, ...]
    quality_flags: tuple[str, ...]
    missing_reason: str | None
    snapshot_hash: str

    @classmethod
    def from_dict(cls, data: dict, snapshot: Snapshot):
        keys = {
            "factor_id", "security_id", "value", "unit", "as_of",
            "lookback_sessions", "evidence_ids", "quality_flags", "missing_reason",
        }
        if not isinstance(data, dict) or set(data) != keys:
            raise ValueError("factor evidence fields do not match schema")
        factor_id = _nonempty(data["factor_id"], "factor_id")
        security_id = _nonempty(data["security_id"], "security_id")
        unit = _nonempty(data["unit"], "unit")
        lookback = data["lookback_sessions"]
        if type(lookback) is not int or lookback < 0:
            raise ValueError("lookback_sessions must be a nonnegative integer")
        evidence = data["evidence_ids"]
        flags = data["quality_flags"]
        if (not isinstance(evidence, list) or not evidence or
                not all(isinstance(item, str) and item for item in evidence) or
                len(evidence) != len(set(evidence))):
            raise ValueError("evidence_ids must be unique visible record IDs")
        if (not isinstance(flags, list) or
                not all(isinstance(item, str) and item for item in flags) or
                len(flags) != len(set(flags))):
            raise ValueError("quality_flags must be unique strings")
        view = snapshot.to_dict()
        as_of = iso(parse_time(data["as_of"]))
        if as_of != view["as_of"]:
            raise ValueError("factor as_of differs from snapshot")
        visible = {row["record_id"] for row in view["records"]}
        if not set(evidence) <= visible:
            raise ValueError("factor refers to invisible evidence")
        reason = data["missing_reason"]
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError("missing_reason must be null or nonempty")
        if (data["value"] is None) == (reason is None):
            raise ValueError("factor requires exactly one of value or missing_reason")
        value = None if data["value"] is None else _decimal_string(data["value"])
        return cls(
            factor_id, security_id, value, unit, as_of, lookback,
            tuple(evidence), tuple(sorted(flags)), reason, snapshot.sha256,
        )

    def to_dict(self):
        return {
            "factor_id": self.factor_id,
            "security_id": self.security_id,
            "value": self.value,
            "unit": self.unit,
            "as_of": self.as_of,
            "lookback_sessions": self.lookback_sessions,
            "evidence_ids": list(self.evidence_ids),
            "quality_flags": list(self.quality_flags),
            "missing_reason": self.missing_reason,
            "snapshot_hash": self.snapshot_hash,
        }


@dataclass(frozen=True)
class FactorFrame:
    snapshot_hash: str
    as_of: str
    evidence: tuple[FactorEvidence, ...]

    @classmethod
    def from_evidence(cls, snapshot: Snapshot, evidence: list[FactorEvidence]):
        if not isinstance(evidence, list):
            raise ValueError("factor evidence must be a list")
        ordered = tuple(sorted(evidence, key=lambda item: (item.factor_id, item.security_id)))
        keys = [(item.factor_id, item.security_id) for item in ordered]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate factor/security key")
        if any(item.snapshot_hash != snapshot.sha256 for item in ordered):
            raise ValueError("factor evidence belongs to another snapshot")
        return cls(snapshot.sha256, snapshot.to_dict()["as_of"], ordered)

    @property
    def sha256(self):
        return digest(self.to_dict())

    def to_dict(self):
        return {
            "snapshot_hash": self.snapshot_hash,
            "as_of": self.as_of,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    def get(self, factor_id: str, security_id: str):
        for item in self.evidence:
            if item.factor_id == factor_id and item.security_id == security_id:
                return item
        raise KeyError((factor_id, security_id))
