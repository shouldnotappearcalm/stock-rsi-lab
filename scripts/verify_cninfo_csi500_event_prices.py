"""Verify event price-pair availability without calculating investment returns."""
import argparse
import json
import re
from bisect import bisect_right
from collections import defaultdict
from datetime import date
from pathlib import Path

from scripts.audit_cninfo_report_admission import END, START, original_report
from scripts.capture_cninfo_csi500_reports_pre2026 import historical_names, member_on, sha256_file
from stock_rsi.qlib_snapshot import QlibSnapshot


def classify_original_events(reports):
    groups = defaultdict(list)
    generic_annual_titles = []
    for kind, rows in reports.items():
        for row in rows:
            title = row["title"]
            if original_report(kind, title):
                years = re.findall(r"20\d{2}", title)
                if not years:
                    raise ValueError("original report title lacks fiscal year")
                groups[(kind, years[-1])].append(row)
            elif kind == "annual" and title.endswith("年报"):
                generic_annual_titles.append(row)
    accepted = []
    ambiguous = []
    for (kind, fiscal_year), rows in sorted(groups.items()):
        if len(rows) == 1:
            accepted.append((kind, rows[0]))
        else:
            ambiguous.append({"kind": kind, "fiscal_year": fiscal_year,
                              "announcement_ids": [row["announcement_id"] for row in rows]})
    return accepted, ambiguous, generic_annual_titles


def check_pair(snapshot, code, announcement_day, intervals, listed_adjustment_dates=()):
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
    if next_day in listed_adjustment_dates:
        return "listed_adjustment_on_open"
    return "price_pair_observed_no_listed_adjustment"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", required=True)
    parser.add_argument("--adjustment-dir", required=True)
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
    adjustment_root = Path(args.adjustment_dir)
    adjustment_manifest_path = adjustment_root / "manifest.json"
    adjustment_manifest = json.loads(adjustment_manifest_path.read_text())
    if adjustment_manifest["status"] != "PRE2026_ADJUSTMENT_METADATA_CAPTURE_ONLY":
        raise ValueError("independent adjustment capture is incomplete")
    if adjustment_manifest["cninfo_plan_sha256"] != sha256_file(plan_path):
        raise ValueError("adjustment and announcement plans differ")
    intervals = historical_names(source.read_text())
    snapshot = QlibSnapshot(args.qlib_root)
    counts = {}
    by_type = {kind: {} for kind in plan["report_categories"]}
    original_events = 0
    ambiguous_groups = []
    generic_annual_rows = 0
    for code in plan["codes"]:
        path = capture / "codes" / (code + ".json")
        if sha256_file(path) != capture_manifest["per_code_sha256"][code]:
            raise ValueError(f"announcement file hash mismatch: {code}")
        data = json.loads(path.read_text())
        adjustment_path = adjustment_root / "codes" / (code + ".json")
        if sha256_file(adjustment_path) != adjustment_manifest["per_code_sha256"][code]:
            raise ValueError(f"adjustment file hash mismatch: {code}")
        adjustments = json.loads(adjustment_path.read_text())
        adjustment_dates = {row["dividOperateDate"] for row in adjustments["events"]}
        accepted, ambiguous, generic = classify_original_events(data["reports"])
        generic_annual_rows += len(generic)
        for group in ambiguous:
            ambiguous_groups.append({"code": code, **group})
            count = len(group["announcement_ids"])
            original_events += count
            counts["ambiguous_report_version"] = counts.get("ambiguous_report_version", 0) + count
            by_type[group["kind"]]["ambiguous_report_version"] = (
                by_type[group["kind"]].get("ambiguous_report_version", 0) + count
            )
        for kind, row in accepted:
            original_events += 1
            status = check_pair(snapshot, code, row["day"], intervals, adjustment_dates)
            counts[status] = counts.get(status, 0) + 1
            by_type[kind][status] = by_type[kind].get(status, 0) + 1
    result = {
        "status": "PRE2026_PRICE_PAIR_ADMISSION_ONLY",
        "window": [START, END], "historical_names": len(plan["codes"]),
        "original_report_events": original_events,
        "ambiguous_report_groups": ambiguous_groups,
        "generic_annual_titles_without_fiscal_year": generic_annual_rows,
        "event_status_counts": counts,
        "event_status_by_report_type": by_type,
        "capture_manifest_sha256": sha256_file(capture_manifest_path),
        "adjustment_manifest_sha256": sha256_file(adjustment_manifest_path),
        "csi500_instruments_sha256": sha256_file(source),
        "qlib_calendar_sha256": sha256_file(Path(args.qlib_root) / "calendars" / "day.txt"),
        "price_source": "QlibSnapshot raw OHLC, no Qlib package",
        "listed_adjustment_source": "BaoStock query_adjust_factor; completeness unproven",
        "return_values_calculated": False,
        "2026_price_or_return_accessed": False,
        "investment_result": None,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items()
                      if key != "ambiguous_report_groups"}, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
