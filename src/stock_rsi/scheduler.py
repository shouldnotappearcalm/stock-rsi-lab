from dataclasses import dataclass
from datetime import datetime

from .calendar import TradingCalendar
from .data import Dataset, digest
from .time import iso, parse_time


@dataclass(frozen=True)
class Wake:
    at: datetime
    reasons: tuple[str, ...]

    @property
    def wake_id(self):
        return digest({"at": iso(self.at), "reasons": self.reasons})

    def to_dict(self):
        return {"at": iso(self.at), "reasons": list(self.reasons), "wake_id": self.wake_id}


def schedule(dataset: Dataset, calendar: TradingCalendar, start: datetime, end: datetime, holding=False):
    start, end = parse_time(start), parse_time(end)
    if start > end:
        raise ValueError("start after end")
    reasons = {}

    def add(at, reason):
        if start <= at <= end:
            reasons.setdefault(at, set()).add(reason)

    previous_week = None
    for day in calendar.days:
        week = day.isocalendar()[:2]
        add(calendar.at(day, "09:00:00"), "PRE_OPEN")
        if week != previous_week:
            add(calendar.at(day, "17:00:00"), "WEEKLY_REVIEW")
        if holding:
            add(calendar.at(day, "17:00:00"), "POSITION_CHECK")
        previous_week = week
    for record in dataset.records:
        if record.kind in ("filing", "announcement"):
            add(record.available_at, "ARRIVAL:" + record.record_id)
    return [Wake(at, tuple(sorted(value))) for at, value in sorted(reasons.items())]
