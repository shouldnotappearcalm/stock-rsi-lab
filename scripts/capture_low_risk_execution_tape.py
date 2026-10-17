"""Capture evaluation-only raw five-minute tape for all frozen order sessions.

These records never enter a decision snapshot or select a strategy. A complete
five-minute day is not an opening-auction order book or a fill guarantee.
"""
import argparse
import json
import socket
from datetime import datetime, timezone
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file
from scripts.capture_low_risk_raw_account_data import query_rows, source_code, numeric


EXPECTED_SUMMARY = "bbae8bdd56c20bf43e702cc45561e79131e650b4b4b2e60a1f25a98494bc7f83"
FIELDS = ("date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag")
SLOTS = tuple(f"{hour:02d}{minute:02d}00000" for hour in (9, 10, 11, 13, 14, 15)
              for minute in range(0, 60, 5)
              if "0935" <= f"{hour:02d}{minute:02d}" <= "1130"
              or "1305" <= f"{hour:02d}{minute:02d}" <= "1500")


def validate_minutes(instrument, day, fields, values):
    if tuple(fields) != FIELDS:
        raise ValueError("five-minute source schema changed")
    datetime.strptime(day, "%Y-%m-%d")
    expected = tuple(day.replace("-", "") + at for at in SLOTS)
    rows = []
    for value in values:
        if len(value) != len(fields):
            raise ValueError("minute column count changed")
        row = dict(zip(fields, value))
        if (row["code"] != source_code(instrument) or row["date"] != day
                or row["time"] not in expected or row["adjustflag"] != "3"):
            raise ValueError("wrong minute security, clock, or raw-price identity")
        for key in ("open", "high", "low", "close", "volume", "amount"):
            if not row[key] or numeric(row[key]) < 0:
                raise ValueError("missing or negative minute numeric field")
        if numeric(row["volume"]) != numeric(row["volume"]).to_integral_value():
            raise ValueError("minute volume must be actual integer shares")
        if numeric(row["volume"]) > 0:
            if (min(numeric(row[key]) for key in ("open", "high", "low", "close")) <= 0
                    or numeric(row["high"]) < max(numeric(row["open"]), numeric(row["close"]))
                    or numeric(row["low"]) > min(numeric(row["open"]), numeric(row["close"]))):
                raise ValueError("invalid traded minute price bounds")
        rows.append(row)
    times = tuple(row["time"] for row in rows)
    if times != tuple(sorted(set(times))):
        raise ValueError("duplicate or unordered minute clock")
    return rows, times == expected


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    replay, output = Path(args.replay_dir), Path(args.output_dir)
    if sha256_file(replay / "summary.json") != EXPECTED_SUMMARY:
        raise ValueError("fixed raw-share replay changed")
    summary = json.loads((replay / "summary.json").read_text())
    requested = set()
    for capital, case in summary["results_by_initial_CNY"].items():
        path = replay / capital / "orders.json"
        if sha256_file(path) != case["artifact_sha256"]["orders.json"]:
            raise ValueError("frozen order source changed")
        for order in json.loads(path.read_text()):
            if order["eligible_at"]:
                at = datetime.fromisoformat(order["eligible_at"])
                if at.utcoffset() is None:
                    raise ValueError("timezone-aware order clock required")
                from zoneinfo import ZoneInfo
                requested.add((order["security_id"], at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()))
    requests = sorted(requested)
    plan = {"status": "FIXED_ORDER_EXECUTION_TAPE_CAPTURE", "summary_sha256": EXPECTED_SUMMARY,
            "capture_code_sha256": sha256_file(__file__), "requests": requests,
            "frequency_minutes": 5, "adjustflag": "3", "used_for_decision": False,
            "auction_volume_inclusion_verified": False, "historical_arrival_verified": False}
    if args.resume:
        if json.loads((output / "plan.json").read_text()) != json.loads(json.dumps(plan)):
            raise ValueError("minute capture resume identity changed")
    else:
        if output.exists():
            raise ValueError("minute capture output already exists")
        (output / "sessions").mkdir(parents=True)
        atomic_json(output / "plan.json", plan)
    import baostock as bs
    socket.setdefaulttimeout(20)
    if bs.login().error_code != "0":
        raise RuntimeError("minute source login failed")
    hashes = {}; complete = empty = total = 0
    try:
        for number, (code, day) in enumerate(requests, 1):
            name = code + "-" + day + ".json"
            path = output / "sessions" / name
            if path.exists():
                packet = json.loads(path.read_text())
                if packet["instrument"] != code or packet["session"] != day:
                    raise ValueError("minute checkpoint identity changed")
                rows, full = validate_minutes(code, day, packet["fields"],
                                             [[row[key] for key in FIELDS] for row in packet["rows"]])
            else:
                fields, raw = query_rows(bs.query_history_k_data_plus(source_code(code), ",".join(FIELDS),
                                        start_date=day, end_date=day, frequency="5", adjustflag="3"))
                rows, full = validate_minutes(code, day, fields, raw)
                atomic_json(path, {"instrument": code, "session": day, "fields": list(FIELDS),
                                   "rows": rows, "complete_48_slots": full,
                                   "observed_at": datetime.now(timezone.utc).isoformat(),
                                   "used_for_decision": False, "historical_arrival_verified": False})
            hashes[name] = sha256_file(path); complete += full; empty += not rows; total += len(rows)
            if number % 25 == 0 or number == len(requests):
                print(json.dumps({"captured": number, "total": len(requests), "complete_sessions": complete,
                                  "empty_sessions": empty, "minute_rows": total}), flush=True)
    finally:
        bs.logout()
    manifest = {**plan, "status": "EVALUATION_ONLY_MINUTE_TAPE_CAPTURED", "requests": len(requests),
                "complete_sessions": complete, "empty_sessions": empty, "minute_rows": total,
                "plan_sha256": sha256_file(output / "plan.json"), "per_session_sha256": hashes}
    atomic_json(output / "manifest.json", manifest)
    print(json.dumps({key: value for key, value in manifest.items() if key != "per_session_sha256"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
