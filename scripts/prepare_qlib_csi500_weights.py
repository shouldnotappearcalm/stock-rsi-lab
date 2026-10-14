"""Build point-in-time Qlib ``$csi500_weight`` feature files from a fixed CSV."""
import argparse
import hashlib
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--source-csv", required=True)
    parser.add_argument("--start", default="2022-12-30")
    parser.add_argument("--end", default="2025-12-30")
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-consumed-2026-diagnostic", action="store_true")
    args = parser.parse_args(argv)
    diagnostic = args.allow_consumed_2026_diagnostic and args.end == "2026-10-13"
    if (args.end >= "2026-01-01" and not diagnostic) or args.start > args.end:
        raise ValueError("weight features must be capped before 2026")

    import numpy as np
    import pandas as pd

    root = Path(args.provider_uri)
    source = Path(args.source_csv)
    calendar = (root / "calendars/day.txt").read_text().splitlines()
    positions = {day: index for index, day in enumerate(calendar)}
    days = [day for day in calendar if args.start <= day <= args.end]
    if not days:
        raise ValueError("requested interval is absent from Qlib calendar")
    frame = pd.read_csv(source, usecols=["index_code", "stock_code", "trade_date", "weight"])
    frame["trade_date"] = pd.to_datetime(frame.trade_date)
    frame = frame[
        (frame.index_code == "000905.SH") & (frame.trade_date <= pd.Timestamp(args.end))
    ].copy()
    if frame.empty:
        raise ValueError("source contains no CSI500 weights before date cap")
    frame["symbol"] = frame.stock_code.str[-2:] + frame.stock_code.str[:6]
    frame["weight"] = frame.weight / 100.0
    pivot = frame.pivot_table(index="trade_date", columns="symbol", values="weight", aggfunc="last").sort_index()
    daily = pivot.reindex(pd.to_datetime(days), method="ffill").fillna(0.0)
    raw_sums = daily.sum(axis=1)
    if (raw_sums <= 0).any():
        raise ValueError("nonpositive CSI500 daily weight sum")
    daily = daily.div(raw_sums, axis=0)
    start_index = positions[days[0]]
    for symbol in daily.columns:
        path = root / "features" / symbol.lower() / "csi500_weight.day.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        values = daily[symbol].to_numpy(dtype="<f4")
        np.concatenate((np.array([start_index], dtype="<f4"), values)).tofile(path)
    sums = daily.sum(axis=1)
    payload = {
        "start": days[0], "end": days[-1], "calendar_days": len(days),
        "symbol_files": len(daily.columns),
        "min_daily_weight_sum": float(sums.min()),
        "max_daily_weight_sum": float(sums.max()),
        "source_rows_used": len(frame),
        "source_max_date_used": str(frame.trade_date.max().date()),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "classification": "CONSUMED_2026_DIAGNOSTIC" if diagnostic else "PRE2026_DEVELOPMENT",
    }
    manifest = Path(args.output)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
