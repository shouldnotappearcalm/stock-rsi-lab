import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .calendar import TradingCalendar
from .time import iso, parse_time


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Record:
    record_id: str
    fact_key: str
    security_id: str
    kind: str
    event_at: datetime
    public_at: datetime
    available_at: datetime
    payload_json: str

    @classmethod
    def from_dict(cls, row):
        event, public, available = (parse_time(row[key]) for key in ("event_at", "public_at", "available_at"))
        if not event <= public <= available:
            raise ValueError("event/public/arrival time order invalid")
        for key in ("record_id", "security_id", "kind"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError(f"nonempty {key} required")
        if row["kind"] == "bar":
            payload = row["payload"]
            for key in ("open", "close"):
                if isinstance(payload.get(key), bool) or not isinstance(payload.get(key), (int, float)) or payload[key] <= 0:
                    raise ValueError("positive finite bar price required")
            if "trade_date" not in payload:
                raise ValueError("bar trade_date required")
        return cls(row["record_id"], row.get("fact_key", row["record_id"]), row["security_id"], row["kind"], event, public, available, canonical(row["payload"]))

    def to_dict(self):
        return {"record_id": self.record_id, "fact_key": self.fact_key, "security_id": self.security_id,
                "kind": self.kind, "event_at": iso(self.event_at), "public_at": iso(self.public_at),
                "available_at": iso(self.available_at), "payload": json.loads(self.payload_json)}


@dataclass(frozen=True)
class Snapshot:
    serialized: str

    @property
    def sha256(self):
        return hashlib.sha256(self.serialized.encode()).hexdigest()

    def to_dict(self):
        return json.loads(self.serialized)


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    evidence_level: str
    provenance_json: str
    sessions: tuple[str, ...]
    records: tuple[Record, ...]
    sha256: str

    @classmethod
    def load(cls, path: str | Path):
        data = json.loads(Path(path).read_text())
        if data.get("evidence_level") not in ("SYNTHETIC_REGRESSION", "REAL_PRICE_ENGINEERING_ONLY", "PIT_RESEARCH_VERIFIED"):
            raise ValueError("explicit dataset evidence level required")
        TradingCalendar(data["sessions"])
        records = tuple(Record.from_dict(row) for row in data["records"])
        ids = [row.record_id for row in records]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate record ID")
        return cls(data["dataset_id"], data["evidence_level"], canonical(data["provenance"]), tuple(sorted(data["sessions"])), records, digest(data))

    @property
    def calendar(self):
        return TradingCalendar(list(self.sessions))

    def snapshot(self, as_of: datetime) -> Snapshot:
        as_of = parse_time(as_of)
        latest = {}
        for record in sorted(self.records, key=lambda row: (row.available_at, row.record_id)):
            if record.available_at <= as_of:
                latest[record.fact_key] = record
        rows = [record.to_dict() for record in sorted(latest.values(), key=lambda row: (row.available_at, row.record_id))]
        return Snapshot(canonical({"dataset_id": self.dataset_id, "evidence_level": self.evidence_level,
                                   "as_of": iso(as_of), "records": rows}))
