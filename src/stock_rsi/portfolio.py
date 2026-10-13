import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

from .data import Snapshot, canonical, digest
from .time import iso, parse_time


WEIGHT_PATTERN = re.compile(r"^(?:0\.\d{6}|1\.000000)$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def account_hash(account: dict) -> str:
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    try:
        return digest(account)
    except (TypeError, ValueError) as exc:
        raise ValueError("account must be canonical JSON") from exc


def _nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"nonempty {name} required")
    return value


def _hash(value, name):
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise ValueError(f"valid {name} required")
    return value


def _money(value, name):
    if isinstance(value, bool):
        raise ValueError(f"finite {name} required")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"finite {name} required") from exc
    if not result.is_finite():
        raise ValueError(f"finite {name} required")
    return result


@dataclass(frozen=True)
class TargetWeight:
    security_id: str
    weight: str

    @classmethod
    def from_dict(cls, data: dict):
        if not isinstance(data, dict) or set(data) != {"security_id", "weight"}:
            raise ValueError("target weight fields do not match schema")
        security_id = _nonempty(data["security_id"], "security_id")
        weight = data["weight"]
        if not isinstance(weight, str) or not WEIGHT_PATTERN.fullmatch(weight):
            raise ValueError("weight must be a six-decimal string in [0, 1]")
        return cls(security_id, weight)

    @property
    def decimal(self):
        return Decimal(self.weight)

    def to_dict(self):
        return {"security_id": self.security_id, "weight": self.weight}


@dataclass(frozen=True)
class PortfolioProposal:
    schema_version: str
    proposal_id: str
    policy_bundle_id: str
    snapshot_hash: str
    account_hash: str
    targets: tuple[TargetWeight, ...]
    horizon_sessions: int
    expires_at: str
    evidence_ids: tuple[str, ...]
    rationale: str
    constraints_json: str
    construction_json: str

    @classmethod
    def from_dict(
        cls,
        data: dict,
        snapshot: Snapshot,
        account: dict,
        eligible: set[str],
        policy_bundle_id: str,
    ):
        keys = {
            "schema_version", "proposal_id", "policy_bundle_id", "snapshot_hash",
            "account_hash", "targets", "horizon_sessions", "expires_at",
            "evidence_ids", "rationale", "constraints", "construction",
        }
        if not isinstance(data, dict) or set(data) != keys:
            raise ValueError("portfolio proposal fields do not match schema")
        if data["schema_version"] != "portfolio-proposal-v1":
            raise ValueError("unsupported portfolio proposal schema")
        proposal_id = _nonempty(data["proposal_id"], "proposal_id")
        expected_policy = _hash(policy_bundle_id, "policy bundle ID")
        supplied_policy = _hash(data["policy_bundle_id"], "policy bundle ID")
        if supplied_policy != expected_policy:
            raise ValueError("proposal belongs to another policy bundle")
        if data["snapshot_hash"] != snapshot.sha256:
            raise ValueError("proposal belongs to another snapshot")
        expected_account = account_hash(account)
        if data["account_hash"] != expected_account:
            raise ValueError("proposal belongs to another account state")
        if not isinstance(eligible, set) or not all(isinstance(item, str) and item for item in eligible):
            raise ValueError("eligible securities must be a set of IDs")
        raw_targets = data["targets"]
        if not isinstance(raw_targets, list) or not raw_targets:
            raise ValueError("proposal requires target weights")
        targets = tuple(sorted((TargetWeight.from_dict(row) for row in raw_targets), key=lambda row: row.security_id))
        securities = [row.security_id for row in targets]
        if len(securities) != len(set(securities)):
            raise ValueError("duplicate target security")
        if securities.count("CASH") != 1:
            raise ValueError("proposal requires exactly one CASH target")
        if any(security != "CASH" and security not in eligible for security in securities):
            raise ValueError("target security is not eligible")
        if sum((row.decimal for row in targets), Decimal(0)) != Decimal("1.000000"):
            raise ValueError("target weights must total exactly 1.000000")
        horizon = data["horizon_sessions"]
        if type(horizon) is not int or horizon < 1:
            raise ValueError("positive horizon_sessions required")
        expires = iso(parse_time(data["expires_at"]))
        if parse_time(expires) <= parse_time(snapshot.to_dict()["as_of"]):
            raise ValueError("proposal expiry must follow its snapshot")
        evidence = data["evidence_ids"]
        if (not isinstance(evidence, list) or not evidence or
                not all(isinstance(item, str) and item for item in evidence) or
                len(evidence) != len(set(evidence))):
            raise ValueError("proposal evidence IDs must be unique strings")
        visible = {row["record_id"] for row in snapshot.to_dict()["records"]}
        if not set(evidence) <= visible:
            raise ValueError("proposal refers to invisible evidence")
        rationale = _nonempty(data["rationale"], "rationale")
        if not isinstance(data["constraints"], dict) or not isinstance(data["construction"], dict):
            raise ValueError("constraints and construction must be objects")
        return cls(
            "portfolio-proposal-v1", proposal_id, supplied_policy, snapshot.sha256,
            expected_account, targets, horizon, expires, tuple(evidence), rationale,
            canonical(data["constraints"]), canonical(data["construction"]),
        )

    @property
    def sha256(self):
        return digest(self.to_dict())

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "policy_bundle_id": self.policy_bundle_id,
            "snapshot_hash": self.snapshot_hash,
            "account_hash": self.account_hash,
            "targets": [row.to_dict() for row in self.targets],
            "horizon_sessions": self.horizon_sessions,
            "expires_at": self.expires_at,
            "evidence_ids": list(self.evidence_ids),
            "rationale": self.rationale,
            "constraints": json.loads(self.constraints_json),
            "construction": json.loads(self.construction_json),
        }


def _millionth_weights(values: dict[str, Decimal], total: Decimal):
    raw = {key: value / total * Decimal(1_000_000) for key, value in values.items()}
    units = {key: int(value.to_integral_value(rounding=ROUND_FLOOR)) for key, value in raw.items()}
    remainder = 1_000_000 - sum(units.values())
    ranked = sorted(values, key=lambda key: (-(raw[key] - units[key]), key))
    for key in ranked[:remainder]:
        units[key] += 1
    return {key: f"{Decimal(units[key]) / Decimal(1_000_000):.6f}" for key in sorted(units)}


def keep_current_proposal(
    snapshot: Snapshot,
    account: dict,
    policy_bundle_id: str,
    evidence_ids: list[str],
    expires_at: datetime,
):
    if not isinstance(account, dict) or not isinstance(account.get("positions"), dict):
        raise ValueError("valid account required")
    cash = _money(account.get("cash"), "cash")
    market_value = _money(account.get("market_value"), "market_value")
    equity = _money(account.get("equity"), "equity")
    if cash < 0 or market_value < 0 or equity <= 0:
        raise ValueError("nonnegative account values and positive equity required")
    values = {"CASH": cash}
    calculated = Decimal(0)
    for security, position in account["positions"].items():
        if not isinstance(position, dict) or position.get("mark_source") != "VISIBLE_PRICE":
            raise ValueError("keep-current requires visible marks")
        quantity = position.get("quantity")
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("positive integer position quantity required")
        value = _money(position.get("mark_price"), "mark_price") * quantity
        if value <= 0:
            raise ValueError("positive marked position value required")
        values[security] = value
        calculated += value
    if calculated != market_value or cash + market_value != equity:
        raise ValueError("account does not conserve marked value")
    weights = _millionth_weights(values, equity)
    payload = {
        "schema_version": "portfolio-proposal-v1",
        "proposal_id": "keep-current",
        "policy_bundle_id": policy_bundle_id,
        "snapshot_hash": snapshot.sha256,
        "account_hash": account_hash(account),
        "targets": [{"security_id": key, "weight": weights[key]} for key in sorted(weights)],
        "horizon_sessions": 1,
        "expires_at": iso(parse_time(expires_at)),
        "evidence_ids": list(evidence_ids),
        "rationale": "retain incumbent portfolio",
        "constraints": {"long_only": True},
        "construction": {"method": "keep-current", "rounding": "largest-remainder-1e-6"},
    }
    return PortfolioProposal.from_dict(payload, snapshot, account, set(account["positions"]), policy_bundle_id)
