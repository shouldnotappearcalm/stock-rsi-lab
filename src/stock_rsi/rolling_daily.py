"""Explicit-window daily-target rolling research with label maturity checks."""
import math
from datetime import date


def rolling_windows(calendar, start, end, history=1210, step=20, horizon=2,
                    permitted_end="2025-12-31"):
    dates = tuple(calendar)
    if not dates or tuple(sorted(set(dates))) != dates or dates[-1].isoformat() > permitted_end:
        raise ValueError("rolling calendar must be explicit, sorted and inside the permitted cap")
    first = dates.index(date.fromisoformat(start))
    last = dates.index(date.fromisoformat(end))
    if first > last or min(history, step, horizon) < 1:
        raise ValueError("invalid rolling range or budget")
    for index in range(first, last + 1, step):
        train_end = index - horizon - 1
        train_start = train_end - history + 1
        if train_start < 0:
            raise ValueError("insufficient past history for fixed rolling window")
        yield {
            "train_start": dates[train_start].isoformat(),
            "train_end": dates[train_end].isoformat(),
            "fit_asof": dates[index - 1].isoformat(),
            "latest_label_maturity": dates[train_end + horizon].isoformat(),
            "prediction_start": dates[index].isoformat(),
            "prediction_end": dates[min(index + step - 1, last)].isoformat(),
        }


class MatureDailyLabels:
    """Compute Qlib's t+1 close-to-t+2 close target only after t+2 closes."""

    def __init__(self, snapshot, calendar):
        self.snapshot = snapshot
        self.calendar = tuple(calendar)
        self.date_index = {day: index for index, day in enumerate(self.calendar)}
        self.cache = {}
        self.latest_read = None

    def targets(self, index, as_of):
        import pandas as pd

        as_of = date.fromisoformat(as_of)
        result = []
        if list(index.names) != ["datetime", "instrument"]:
            raise ValueError("daily targets require datetime/instrument rows")
        marker = pd.Series(range(len(index)), index=index)
        for at, group in marker.groupby(level="datetime", sort=True):
            day = at.date()
            position = self.date_index[day]
            if position + 2 >= len(self.calendar) or self.calendar[position + 2] > as_of:
                raise ValueError("training label has not matured by fit time")
            symbols = tuple(group.index.get_level_values("instrument"))
            if day in self.cache:
                known_symbols, cached = self.cache[day]
                if known_symbols != symbols:
                    raise ValueError("training-day universe changed under the label cache")
                result.append(cached)
                continue
            next_day, maturity = self.calendar[position + 1], self.calendar[position + 2]
            values = []
            for symbol in symbols:
                first = self.snapshot.value(symbol, "close", next_day.isoformat())
                second = self.snapshot.value(symbol, "close", maturity.isoformat())
                value = (second / first - 1 if first is not None and second is not None
                         and math.isfinite(first) and math.isfinite(second) and first > 0 and second > 0
                         else float("nan"))
                values.append(value)
            self.latest_read = max(maturity, self.latest_read or maturity)
            raw = pd.Series(values, index=group.index, dtype="float32")
            normalized = (raw.rank(pct=True) - 0.5) * 3.46
            self.cache[day] = (symbols, normalized)
            result.append(normalized)
        return pd.concat(result).reindex(index)
