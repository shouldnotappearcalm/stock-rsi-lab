"""Capture pre-2026 CNINFO report metadata for historical CSI500 main-board names.

This is an append-only data acquisition step, not a signal or backtest. A
current CNINFO organization map is frozen in the local capture plan and must
not be mistaken for a point-in-time security master. Interrupted runs resume
only with the same input file, plan, and completed per-stock snapshots.
"""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from scripts.audit_cninfo_report_admission import (
    CNINFO, END, REPORT_CATEGORIES, START, original_report, query, request_json,
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def historical_names(instrument_text):
    intervals = {}
    for line in instrument_text.splitlines():
        code, start, end = line.split()
        if start <= END and end >= START and (code.startswith("SH60") or code.startswith("SZ00")):
            intervals.setdefault(code, []).append((start, end))
    return {code: sorted(spans) for code, spans in sorted(intervals.items())}


def member_on(code, day, intervals):
    return any(start <= day <= end for start, end in intervals.get(code, []))


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.replace(temp, path)


class RateLimitedClient:
    def __init__(self, interval):
        self.interval = interval
        self.next_request = 0.0
        self.requests = 0

    def fetch(self, url, payload=None):
        last_error = None
        for attempt in range(3):
            delay = self.next_request - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            try:
                result = request_json(url, payload)
                self.requests += 1
                self.next_request = time.monotonic() + self.interval
                return result
            except (OSError, ValueError) as exc:
                last_error = exc
                self.next_request = time.monotonic() + max(self.interval, 1 << attempt)
        raise RuntimeError("CNINFO request failed after three bounded attempts") from last_error


def capture_one(code, org, client):
    reports = {
        kind: query(org, code[2:], category, max_pages=5, fetch=client.fetch)
        for kind, category in REPORT_CATEGORIES.items()
    }
    category_counts = {kind: len(rows) for kind, rows in reports.items()}
    recoveries = []
    missing = []
    for kind in REPORT_CATEGORIES:
        for year in ("2024", "2025"):
            if any(row["day"].startswith(year) and original_report(kind, row["title"])
                   for row in reports[kind]):
                continue
            fulltext = query(org, code[2:], "", year + "-01-01", year + "-12-31",
                             max_pages=20, fetch=client.fetch)
            known = {row["announcement_id"] for row in reports[kind]}
            matches = [row for row in fulltext if original_report(kind, row["title"])]
            for row in matches:
                if row["announcement_id"] not in known:
                    reports[kind].append(row)
                    recoveries.append({"kind": kind, "year": year,
                                       "announcement_id": row["announcement_id"]})
                    known.add(row["announcement_id"])
            if not matches:
                missing.append({"kind": kind, "year": year})
    ids = [row["announcement_id"] for rows in reports.values() for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate announcement ID across categories for {code}")
    return {
        "code": code, "query_window": [START, END], "category_counts": category_counts,
        "reports": reports, "fallback_recoveries": recoveries,
        "missing_original_reports": missing,
    }


def summarize_capture(output, plan, intervals, requests):
    counts = {kind: 0 for kind in REPORT_CATEGORIES}
    original = {kind: 0 for kind in REPORT_CATEGORIES}
    eligible = {kind: 0 for kind in REPORT_CATEGORIES}
    recovery = []
    missing = []
    midnight = 0
    total = 0
    hashes = {}
    for code in plan["codes"]:
        path = output / "codes" / (code + ".json")
        if not path.is_file():
            raise ValueError(f"capture incomplete: {code}")
        data = json.loads(path.read_text())
        if data["code"] != code or data["query_window"] != [START, END]:
            raise ValueError(f"capture checkpoint mismatch: {code}")
        hashes[code] = sha256_file(path)
        recovery.extend({"code": code, **item} for item in data["fallback_recoveries"])
        missing.extend({"code": code, **item} for item in data["missing_original_reports"])
        for kind, rows in data["reports"].items():
            counts[kind] += len(rows)
            for row in rows:
                total += 1
                midnight += int((row["timestamp_ms"] + 8 * 3_600_000) % 86_400_000 == 0)
                if original_report(kind, row["title"]):
                    original[kind] += 1
                    if member_on(code, row["day"], intervals):
                        eligible[kind] += 1
    result = {
        "status": "PRE2026_EVENT_METADATA_CAPTURE_ONLY",
        "window": [START, END], "historical_universe": "CSI500 main-board membership intervals",
        "unique_names": len(plan["codes"]),
        "report_rows_by_category": counts,
        "original_reports_by_category": original,
        "original_reports_during_membership": eligible,
        "all_report_rows": total,
        "midnight_timestamp_rows": midnight,
        "fulltext_recoveries": recovery,
        "missing_original_report_cells": missing,
        "requests_this_invocation": requests,
        "input_instrument_sha256": plan["input_instrument_sha256"],
        "plan_sha256": sha256_file(output / "plan.json"),
        "per_code_sha256": hashes,
        "current_organization_lookup_used": True,
        "current_lookup_is_historical_security_master": False,
        "availability_rule": "date-only; visible after announcement-day close",
        "2026_price_or_return_accessed": False,
        "investment_result": None,
    }
    atomic_json(output / "manifest.json", result)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("per_code_sha256", "fulltext_recoveries", "missing_original_report_cells")},
                     ensure_ascii=False, indent=2), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--csi500-instruments", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--request-interval", type=float, default=0.2)
    args = parser.parse_args(argv)
    if args.request_interval < 0.1:
        raise ValueError("CNINFO request interval must be at least 0.1 second")
    source = Path(args.csi500_instruments)
    output = Path(args.output_dir)
    intervals = historical_names(source.read_text())
    codes = list(intervals)
    source_hash = sha256_file(source)
    client = RateLimitedClient(args.request_interval)
    if args.resume:
        if not (output / "plan.json").is_file():
            raise ValueError("resume requires an existing capture plan")
        plan = json.loads((output / "plan.json").read_text())
        if plan["codes"] != codes or plan["input_instrument_sha256"] != source_hash:
            raise ValueError("resume input differs from the frozen plan")
    else:
        if output.exists():
            raise ValueError("output directory already exists")
        listing = client.fetch(CNINFO + "/new/data/szse_stock.json")["stockList"]
        org = {item["code"]: item["orgId"] for item in listing}
        missing = [code for code in codes if code[2:] not in org]
        if missing:
            raise ValueError(f"current CNINFO organization map misses {len(missing)} historical names")
        plan = {"status": "FROZEN_CAPTURE_PLAN", "window": [START, END],
                "codes": codes, "org_by_code": {code: org[code[2:]] for code in codes},
                "report_categories": REPORT_CATEGORIES,
                "input_instrument_sha256": source_hash,
                "current_organization_lookup_used": True}
        (output / "codes").mkdir(parents=True)
        atomic_json(output / "plan.json", plan)
    if plan["window"] != [START, END] or plan["report_categories"] != REPORT_CATEGORIES:
        raise ValueError("capture plan does not match this implementation")
    completed = 0
    for code in codes:
        path = output / "codes" / (code + ".json")
        if path.exists():
            saved = json.loads(path.read_text())
            if saved["code"] != code or saved["query_window"] != [START, END]:
                raise ValueError(f"invalid checkpoint for {code}")
        else:
            atomic_json(path, capture_one(code, plan["org_by_code"][code], client))
        completed += 1
        if completed % 25 == 0 or completed == len(codes):
            print(json.dumps({"completed": completed, "total": len(codes),
                              "requests": client.requests}), flush=True)
    summarize_capture(output, plan, intervals, client.requests)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
