from __future__ import annotations

import argparse
import json
import math
import struct
from dataclasses import dataclass
from datetime import date
from pathlib import Path


_EQUITY_PREFIXES = {
    "SH": ("600", "601", "603", "605", "688", "689"),
    "SZ": ("000", "001", "002", "003", "300", "301"),
    "BJ": ("4", "8", "9"),
}
_MAINBOARD_PREFIXES = ("SH600", "SH601", "SH603", "SH605", "SZ000", "SZ001", "SZ002", "SZ003")


def _day(value: str) -> date:
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return parsed


def equity_exchange(symbol: str) -> str | None:
    """Classify exchange-prefixed A-share symbols and reject indices/B shares."""
    if not isinstance(symbol, str) or len(symbol) != 8:
        return None
    exchange, code = symbol[:2].upper(), symbol[2:]
    if not code.isdigit():
        return None
    prefixes = _EQUITY_PREFIXES.get(exchange)
    if prefixes is None or not code.startswith(prefixes):
        return None
    return exchange


@dataclass(frozen=True)
class InstrumentRange:
    symbol: str
    start: date
    end: date


class QlibSnapshot:
    """Read a fixed Qlib binary snapshot without depending on the qlib package.

    Qlib's CN daily normalizer stores adjusted prices divided by the first
    adjusted close, a similarly normalized factor, and inversely adjusted
    volume. Raw values are therefore recovered as price/factor and
    volume*factor. Amount is preserved by investment_data's normalizer.
    """

    REQUIRED_FIELDS = ("open", "high", "low", "close", "volume", "factor")

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.calendar = self._load_calendar()
        self._calendar_index = {value: index for index, value in enumerate(self.calendar)}
        self.instruments = self._load_instruments()
        self._feature_cache: dict[tuple[str, str], tuple[int, tuple[float, ...]]] = {}

    def _load_calendar(self) -> tuple[date, ...]:
        path = self.root / "calendars" / "day.txt"
        if not path.is_file():
            raise ValueError(f"missing Qlib calendar: {path}")
        values = tuple(_day(line) for line in path.read_text().splitlines() if line)
        if not values or values != tuple(sorted(set(values))):
            raise ValueError("Qlib calendar must be nonempty, unique and sorted")
        return values

    def _load_instruments(self) -> tuple[InstrumentRange, ...]:
        path = self.root / "instruments" / "all.txt"
        if not path.is_file():
            raise ValueError(f"missing Qlib instruments: {path}")
        ranges = []
        seen = set()
        for line in path.read_text().splitlines():
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                raise ValueError(f"invalid Qlib instrument row: {line!r}")
            symbol = parts[0].upper()
            item = InstrumentRange(symbol, _day(parts[1]), _day(parts[2]))
            if item.start > item.end or (symbol, item.start, item.end) in seen:
                raise ValueError(f"invalid Qlib instrument interval: {line!r}")
            seen.add((symbol, item.start, item.end))
            ranges.append(item)
        if not ranges:
            raise ValueError("Qlib instrument set must be nonempty")
        return tuple(ranges)

    def equities_on(self, trade_date: str, exchanges=("SH", "SZ", "BJ")) -> tuple[str, ...]:
        target = _day(trade_date)
        exchanges = tuple(value.upper() for value in exchanges)
        unknown = set(exchanges) - set(_EQUITY_PREFIXES)
        if unknown:
            raise ValueError(f"unknown exchanges: {sorted(unknown)}")
        return tuple(sorted({
            item.symbol for item in self.instruments
            if item.start <= target <= item.end and equity_exchange(item.symbol) in exchanges
        }))

    def mainboard_sh_sz_on(self, trade_date: str) -> tuple[str, ...]:
        target = _day(trade_date)
        return tuple(sorted({
            item.symbol for item in self.instruments
            if item.start <= target <= item.end and item.symbol.startswith(_MAINBOARD_PREFIXES)
        }))

    def _feature(self, symbol: str, field: str) -> tuple[int, tuple[float, ...]]:
        symbol = symbol.upper()
        if field not in self.REQUIRED_FIELDS + ("amount", "adjclose", "vwap", "change"):
            raise ValueError(f"unsupported Qlib field: {field}")
        key = (symbol, field)
        if key in self._feature_cache:
            return self._feature_cache[key]
        path = self.root / "features" / symbol.lower() / f"{field}.day.bin"
        if not path.is_file():
            raise ValueError(f"missing Qlib feature: {path}")
        raw = path.read_bytes()
        if len(raw) < 8 or len(raw) % 4:
            raise ValueError(f"invalid Qlib feature length: {path}")
        values = struct.unpack(f"<{len(raw) // 4}f", raw)
        first = values[0]
        start = int(first)
        if start != first or start < 0 or start >= len(self.calendar):
            raise ValueError(f"invalid Qlib feature start index: {path}")
        if start + len(values) - 1 > len(self.calendar):
            raise ValueError(f"Qlib feature extends beyond calendar: {path}")
        result = (start, tuple(values[1:]))
        self._feature_cache[key] = result
        return result

    def value(self, symbol: str, field: str, trade_date: str) -> float | None:
        target = _day(trade_date)
        calendar_index = self._calendar_index.get(target)
        if calendar_index is None:
            raise ValueError(f"date is not in Qlib calendar: {trade_date}")
        start, values = self._feature(symbol, field)
        offset = calendar_index - start
        if offset < 0 or offset >= len(values):
            return None
        value = values[offset]
        return value if math.isfinite(value) else None

    def raw_bar(self, symbol: str, trade_date: str) -> dict:
        symbol = symbol.upper()
        target = _day(trade_date)
        exchange = equity_exchange(symbol)
        if exchange is None:
            raise ValueError(f"not an A-share equity symbol: {symbol}")
        active = any(item.symbol == symbol and item.start <= target <= item.end for item in self.instruments)
        if not active:
            return {"symbol": symbol, "trade_date": trade_date, "status": "outside_observed_range"}
        values = {field: self.value(symbol, field, trade_date) for field in self.REQUIRED_FIELDS}
        factor = values["factor"]
        required = tuple(values[field] for field in ("open", "high", "low", "close", "volume"))
        if factor is None or factor <= 0 or any(value is None for value in required):
            return {
                "symbol": symbol,
                "trade_date": trade_date,
                "status": "missing_or_suspended",
                "tradable": None,
            }
        prices = {field: values[field] / factor for field in ("open", "high", "low", "close")}
        if any(not math.isfinite(value) or value <= 0 for value in prices.values()):
            raise ValueError(f"invalid reconstructed price for {symbol} on {trade_date}")
        amount = self.value(symbol, "amount", trade_date)
        return {
            "symbol": symbol,
            "exchange": exchange,
            "trade_date": trade_date,
            "status": "observed_bar",
            **prices,
            "volume_source_units": values["volume"] * factor,
            "amount_source_units": amount,
            "normalization_factor": factor,
            "tradable": None,
        }

    def audit(self, trade_date: str, symbols=()) -> dict:
        target = _day(trade_date)
        if target not in self._calendar_index:
            raise ValueError(f"date is not in Qlib calendar: {trade_date}")
        exchange_counts = {
            exchange: len(self.equities_on(trade_date, (exchange,)))
            for exchange in _EQUITY_PREFIXES
        }
        observed = [item for item in self.instruments if item.start <= target <= item.end]
        return {
            "root": str(self.root.resolve()),
            "trade_date": trade_date,
            "calendar_start": self.calendar[0].isoformat(),
            "calendar_end": self.calendar[-1].isoformat(),
            "instrument_rows": len(self.instruments),
            "observed_instruments": len({item.symbol for item in observed}),
            "a_share_equities": sum(exchange_counts.values()),
            "a_share_by_exchange": exchange_counts,
            "mainboard_sh_sz_equities": len(self.mainboard_sh_sz_on(trade_date)),
            "samples": [self.raw_bar(symbol, trade_date) for symbol in symbols],
            "evidence_level": "REAL_PRICE_ENGINEERING_ONLY",
            "limitations": [
                "instrument intervals are first/last observed bars, not authoritative listing status",
                "missing bars do not distinguish suspension from source gaps",
                "tradability requires a separate point-in-time suspension and price-limit table",
                "financial publication and revision history is absent",
                "volume and amount retain upstream source units and need a separate unit contract",
            ],
        }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stock-rsi-qlib-audit")
    parser.add_argument("--root", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--symbols", default="")
    args = parser.parse_args(argv)
    symbols = tuple(value.strip().upper() for value in args.symbols.split(",") if value.strip())
    try:
        report = QlibSnapshot(args.root).audit(args.date, symbols)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
