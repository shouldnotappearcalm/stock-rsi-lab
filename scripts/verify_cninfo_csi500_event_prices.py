"""Verify event price-pair availability without calculating investment returns."""
import argparse
import json
from bisect import bisect_right
from datetime import date
from pathlib import Path

from scripts.audit_cninfo_report_admission import END, START, original_report
from scripts.capture_cninfo_csi500_reports_pre2026 import historical_names, member_on, sha256_file
from stock_rsi.qlib_snapshot import QlibSnapshot


def check_pair(snapshot, code, announcement_day, intervals):
    event_date = date.fromisoformat(announcement_day)
    if event_date.isoformat() != announcement_day or not START <= announcement_day <= END:
        raise ValueError("announcement outside pre-2026 interval")
    calendar = snapshot.calendar
    next_index = bisect_right(calendar, event_date)
    if next_index >= len(calendar) or calendar[next_index].isoformat() > END:
        return "no_pre2026_next_session"
    if next_index < 1:
        return "no_previous_session"
    next_day = calendar[next_index].isoformat()
    previous_day = calendar[next_index - 1].isoformat()
    if not member_on(code, next_day, intervals):
        return "outside_csi500_on_signal_day"
    previous = snapshot.raw_bar(code, previous_day)
    opening = snapshot.raw_bar(code, next_day)
    if previous["status"] != "observed_bar" or opening["status"] != "observed_bar":
        return "missing_or_suspended_price"
    before_factor = previous["normalization_factor"]
    after_factor = opening["normalization_factor"]
    if abs(after_factor / before_factor - 1) > 1e-5:
        return "corporate_action_factor_jump"
    return "price_pair_admitted"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", required=True)
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
    plan = json.loads(plan_path.read_text())
    capture_manifest = json.loads(capture_manifest_path.read_text())
    if capture_manifest["status"] != "PRE2026_EVENT_METADATA_CAPTURE_ONLY":
        raise ValueError("CNINFO capture is incomplete")
    source = Path(args.csi500_instruments)
    if sha256_file(source) != plan["input_instrument_sha256"]:
        raise ValueError("membership input differs from capture plan")
    intervals = historical_names(source.read_text())
    snapshot = QlibSnapshot(args.qlib_root)
    counts = {}
    by_type = {kind: {} for kind in plan["report_categories"]}
    original_events = 0
    for code in plan["codes"]:
        path = capture / "codes" / (code + ".json")
        if sha256_file(path) != capture_manifest["per_code_sha256"][code]:
            raise ValueError(f"announcement file hash mismatch: {code}")
        data = json.loads(path.read_text())
        for kind, rows in data["reports"].items():
            for row in rows:
                if not original_report(kind, row["title"]):
                    continue
                original_events += 1
                status = check_pair(snapshot, code, row["day"], intervals)
                counts[status] = counts.get(status, 0) + 1
                by_type[kind][status] = by_type[kind].get(status, 0) + 1
    result = {
        "status": "PRE2026_PRICE_PAIR_ADMISSION_ONLY",
        "window": [START, END], "historical_names": len(plan["codes"]),
        "original_report_events": original_events,
        "event_status_counts": counts,
        "event_status_by_report_type": by_type,
        "capture_manifest_sha256": sha256_file(capture_manifest_path),
        "csi500_instruments_sha256": sha256_file(source),
        "qlib_calendar_sha256": sha256_file(Path(args.qlib_root) / "calendars" / "day.txt"),
        "price_source": "QlibSnapshot raw OHLC and factor, no Qlib package",
        "return_values_calculated": False,
        "2026_price_or_return_accessed": False,
        "investment_result": None,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
