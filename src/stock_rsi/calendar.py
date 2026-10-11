from datetime import date, datetime
from zoneinfo import ZoneInfo

from .time import parse_time

SHANGHAI = ZoneInfo("Asia/Shanghai")


class TradingCalendar:
    """Explicit exchange sessions; no weekday inference."""

    def __init__(self, sessions: list[str]):
        self.days = tuple(sorted(date.fromisoformat(day) for day in sessions))
        if len(self.days) != len(set(self.days)):
            raise ValueError("duplicate trading day")
        if any(day.weekday() >= 5 for day in self.days):
            raise ValueError("A-share weekend session is invalid")

    def at(self, day: date, clock: str) -> datetime:
        return parse_time(datetime.fromisoformat(f"{day.isoformat()}T{clock}").replace(tzinfo=SHANGHAI))

    def is_trading(self, at: datetime) -> bool:
        local = parse_time(at).astimezone(SHANGHAI)
        if local.date() not in self.days:
            return False
        clock = local.strftime("%H:%M:%S")
        return "09:30:00" <= clock < "11:30:00" or "13:00:00" <= clock < "15:00:00"

    def next_open(self, after: datetime) -> datetime:
        after = parse_time(after)
        for day in self.days:
            for clock in ("09:30:00", "13:00:00"):
                candidate = self.at(day, clock)
                if candidate > after:
                    return candidate
        raise ValueError("calendar exhausted")

    def next_day_open(self, after: datetime) -> datetime:
        after = parse_time(after)
        for day in self.days:
            candidate = self.at(day, "09:30:00")
            if candidate > after:
                return candidate
        raise ValueError("calendar exhausted")
