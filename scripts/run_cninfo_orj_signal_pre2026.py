"""One fixed, development-only test of announcement overnight response.

This is an event-signal diagnostic, not an investable backtest. It reads no
2026 prices and never selects a holding horizon or threshold from the result.
"""
import argparse
import hashlib
import json
import math
from bisect import bisect_right
from collections import defaultdict
from datetime import date
from pathlib import Path

from scripts.audit_cninfo_report_admission import END, START
from scripts.capture_cninfo_csi500_reports_pre2026 import historical_names, sha256_file
from scripts.verify_cninfo_csi500_event_prices import check_pair, classify_original_events
from stock_rsi.qlib_snapshot import QlibSnapshot


HORIZONS = (20, 60)
ROUND_TRIP_COST = 0.002  # Qlib 5 bp buy + 15 bp sell, simplified
BENCHMARK = "SH000905"
EXPECTED_CAPTURE_SHA256 = "3adcf64870b6300be87bed4ebddc216b2ed3c0619d3f99a795698f2bc6bf2eb2"
EXPECTED_ADJUSTMENT_SHA256 = "bdd17e0567e8c22197cbc4e17765f2cb7ab7378cb8d1465a0d48cb120ec6e225"
EXPECTED_ADMISSION_SHA256 = "56e1b313f39eab862f00849ac00b1200969881f7442a76b66a71dbd451f6fd79"
EXPECTED_MEMBERSHIP_SHA256 = "ea377505b12eaeb234122b8b7523bbce0d38d4783090cbee2c47da44a9b61c35"
EXPECTED_CALENDAR_SHA256 = "cfd6b5517b418f3979790136389f6fdcf27be60000b04bad9d65814e961e8867"
EXPECTED_PRICE_INPUTS_SHA256 = "ab0357340ad07bedf4a4ceda8bd22cde759400d6d92b86ee4a31b4ab649e62c4"


def price_input_digest(root, codes):
    root = Path(root)
    digest = hashlib.sha256()
    files = [Path("instruments/all.txt")]
    for code in sorted(codes):
        files.extend(Path("features") / code.lower() / (field + ".day.bin")
                     for field in ("open", "high", "low", "close", "volume", "factor", "amount", "adjclose"))
    files.append(Path("features/sh000905/adjclose.day.bin"))
    for relative in files:
        digest.update(relative.as_posix().encode() + b"\0")
        with (root / relative).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def next_sessions(calendar, announcement_day):
    index = bisect_right(calendar, date.fromisoformat(announcement_day))
    if index + 1 >= len(calendar):
        return None
    signal = calendar[index].isoformat()
    entry = calendar[index + 1].isoformat()
    if entry > END:
        return None
    return signal, entry, index + 1


def finite_price(snapshot, symbol, day):
    value = snapshot.value(symbol, "adjclose", day)
    return value if value is not None and math.isfinite(value) and value > 0 else None


def summarize_horizon(events, snapshot, horizon):
    groups = {"positive": [], "nonpositive": []}
    skipped = defaultdict(int)
    calendar = snapshot.calendar
    for event in events:
        exit_index = event["entry_index"] + horizon
        if exit_index >= len(calendar) or calendar[exit_index].isoformat() > END:
            skipped["censored_at_2025"] += 1
            continue
        end = calendar[exit_index].isoformat()
        start = event["entry_day"]
        prices = [finite_price(snapshot, event["code"], start),
                  finite_price(snapshot, event["code"], end),
                  finite_price(snapshot, BENCHMARK, start),
                  finite_price(snapshot, BENCHMARK, end)]
        if any(value is None for value in prices):
            skipped["missing_adjusted_price"] += 1
            continue
        stock_return = prices[1] / prices[0] - 1
        benchmark_return = prices[3] / prices[2] - 1
        excess = stock_return - benchmark_return - ROUND_TRIP_COST
        bucket = "positive" if event["overnight_response"] > 0 else "nonpositive"
        groups[bucket].append((event["signal_day"], stock_return, benchmark_return, excess))

    result = {}
    for bucket, values in groups.items():
        by_date = defaultdict(list)
        for signal_day, _, _, excess in values:
            by_date[signal_day].append(excess)
        result[bucket] = {
            "events": len(values), "distinct_signal_days": len(by_date),
            "mean_gross_return_pct": sum(item[1] for item in values) / len(values) * 100 if values else None,
            "mean_benchmark_return_pct": sum(item[2] for item in values) / len(values) * 100 if values else None,
            "mean_cost_adjusted_excess_pct": sum(item[3] for item in values) / len(values) * 100 if values else None,
            "date_balanced_cost_adjusted_excess_pct": (
                sum(sum(day_values) / len(day_values) for day_values in by_date.values())
                / len(by_date) * 100 if by_date else None
            ),
        }
    positive = result["positive"]["mean_cost_adjusted_excess_pct"]
    nonpositive = result["nonpositive"]["mean_cost_adjusted_excess_pct"]
    result["positive_minus_nonpositive_excess_points"] = (
        positive - nonpositive if positive is not None and nonpositive is not None else None
    )
    result["skipped"] = dict(skipped)
    return result


def development_lead_status(results):
    primary = results["60"]
    secondary = results["20"]
    positive = primary["positive"]
    if (positive["events"] < 100 or positive["distinct_signal_days"] < 40):
        return "REJECTED_INSUFFICIENT_EVENT_COVERAGE"
    if (primary["positive_minus_nonpositive_excess_points"] is None
            or primary["positive_minus_nonpositive_excess_points"] <= 0
            or positive["date_balanced_cost_adjusted_excess_pct"] is None
            or positive["date_balanced_cost_adjusted_excess_pct"] <= 0
            or secondary["positive"]["date_balanced_cost_adjusted_excess_pct"] is None
            or secondary["positive"]["date_balanced_cost_adjusted_excess_pct"] <= 0):
        return "REJECTED_DEVELOPMENT_SIGNAL"
    return "DEVELOPMENT_LEAD_ONLY_NO_PORTFOLIO_CLAIM"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", required=True)
    parser.add_argument("--adjustment-dir", required=True)
    parser.add_argument("--price-admission", required=True)
    parser.add_argument("--csi500-instruments", required=True)
    parser.add_argument("--qlib-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists():
        raise ValueError("output already exists")
    capture = Path(args.capture_dir)
    plan_path = capture / "plan.json"
    capture_manifest_path = capture / "manifest.json"
    adjustment_manifest_path = Path(args.adjustment_dir) / "manifest.json"
    admission_path = Path(args.price_admission)
    plan = json.loads(plan_path.read_text())
    if EXPECTED_PRICE_INPUTS_SHA256.startswith("TO_BE_"):
        raise ValueError("price inputs must be frozen before signal evaluation")
    capture_manifest = json.loads(capture_manifest_path.read_text())
    adjustment_manifest = json.loads(adjustment_manifest_path.read_text())
    admission = json.loads(admission_path.read_text())
    for path, expected in (
        (capture_manifest_path, EXPECTED_CAPTURE_SHA256),
        (adjustment_manifest_path, EXPECTED_ADJUSTMENT_SHA256),
        (admission_path, EXPECTED_ADMISSION_SHA256),
        (Path(args.csi500_instruments), EXPECTED_MEMBERSHIP_SHA256),
        (Path(args.qlib_root) / "calendars" / "day.txt", EXPECTED_CALENDAR_SHA256),
    ):
        if sha256_file(path) != expected:
            raise ValueError(f"frozen ORJ input hash mismatch: {path}")
    if admission["status"] != "PRE2026_PRICE_PAIR_ADMISSION_ONLY":
        raise ValueError("event price admission has not passed")
    if (admission["capture_manifest_sha256"] != sha256_file(capture_manifest_path)
            or admission["adjustment_manifest_sha256"] != sha256_file(adjustment_manifest_path)):
        raise ValueError("data admission hashes differ from the input captures")
    instrument_path = Path(args.csi500_instruments)
    if sha256_file(instrument_path) != plan["input_instrument_sha256"]:
        raise ValueError("historical membership input changed")
    if price_input_digest(args.qlib_root, plan["codes"]) != EXPECTED_PRICE_INPUTS_SHA256:
        raise ValueError("frozen Qlib price inputs changed")
    intervals = historical_names(instrument_path.read_text())
    snapshot = QlibSnapshot(args.qlib_root)
    events_by_stock_signal = {}
    excluded = defaultdict(int)
    for code in plan["codes"]:
        announcement_path = capture / "codes" / (code + ".json")
        adjustment_path = Path(args.adjustment_dir) / "codes" / (code + ".json")
        if (sha256_file(announcement_path) != capture_manifest["per_code_sha256"][code]
                or sha256_file(adjustment_path) != adjustment_manifest["per_code_sha256"][code]):
            raise ValueError(f"input event hash changed: {code}")
        reports = json.loads(announcement_path.read_text())["reports"]
        adjustment_dates = {row["dividOperateDate"] for row in
                            json.loads(adjustment_path.read_text())["events"]}
        accepted, ambiguous, generic = classify_original_events(reports)
        excluded["ambiguous_original_rows"] += sum(len(item["announcement_ids"]) for item in ambiguous)
        excluded["generic_yearless_annual_rows"] += len(generic)
        for kind, row in accepted:
            status = check_pair(snapshot, code, row["day"], intervals, adjustment_dates)
            if status != "price_pair_observed_no_listed_adjustment":
                excluded[status] += 1
                continue
            session = next_sessions(snapshot.calendar, row["day"])
            if session is None:
                excluded["no_pre2026_entry_session"] += 1
                continue
            signal_day, entry_day, entry_index = session
            index = bisect_right(snapshot.calendar, date.fromisoformat(row["day"]))
            previous_day = snapshot.calendar[index - 1].isoformat()
            previous_close = snapshot.raw_bar(code, previous_day)["close"]
            next_open = snapshot.raw_bar(code, signal_day)["open"]
            overnight_response = next_open / previous_close - 1
            key = (code, signal_day)
            if key in events_by_stock_signal:
                events_by_stock_signal[key]["report_types"].add(kind)
                excluded["same_stock_signal_day_deduplicated"] += 1
            else:
                events_by_stock_signal[key] = {
                    "code": code, "signal_day": signal_day,
                    "entry_day": entry_day, "entry_index": entry_index,
                    "overnight_response": overnight_response,
                    "report_types": {kind},
                }
    events = list(events_by_stock_signal.values())
    results = {str(horizon): summarize_horizon(events, snapshot, horizon) for horizon in HORIZONS}
    result = {
        "status": "PRE2026_DEVELOPMENT_SIGNAL_DIAGNOSTIC_ONLY",
        "candidate_budget": 1, "window": [START, END],
        "rule": "date-only report; after next open ORJ=(next open/previous close)-1; entry following close",
        "primary_horizon_sessions": 60, "secondary_horizon_sessions": 20,
        "round_trip_cost_assumption": ROUND_TRIP_COST,
        "benchmark": BENCHMARK,
        "deduplicated_signal_events": len(events),
        "excluded": dict(excluded), "results": results,
        "diagnostic_status": development_lead_status(results),
        "capture_manifest_sha256": sha256_file(capture_manifest_path),
        "adjustment_manifest_sha256": sha256_file(adjustment_manifest_path),
        "price_admission_sha256": sha256_file(admission_path),
        "membership_sha256": sha256_file(instrument_path),
        "qlib_calendar_sha256": sha256_file(Path(args.qlib_root) / "calendars" / "day.txt"),
        "price_input_digest_sha256": EXPECTED_PRICE_INPUTS_SHA256,
        "2026_price_or_return_accessed": False,
        "investable_portfolio_return": None,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
