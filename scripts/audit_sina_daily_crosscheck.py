"""Exact daily OHLCV comparison without feeding new data into policy/replay."""
import argparse
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from scripts.capture_sina_daily_crosscheck import EXPECTED_RAW_MANIFEST, FIELDS, validate_sina_daily
from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file


def compare_security(raw_bars, rows):
    source = {row["day"]: row for row in rows}
    missing = []; differences = []; halted_conflicts = []; compared = 0
    for raw in raw_bars:
        day = raw["date"]; other = source.get(day)
        if raw["tradestatus"] == "0":
            if other is not None and Decimal(other["volume"]) > 0:
                halted_conflicts.append(day)
            continue
        if other is None:
            missing.append(day); continue
        compared += 1
        for field in FIELDS:
            if Decimal(raw[field]) != Decimal(other[field]):
                differences.append({"day": day, "field": field, "original": raw[field], "sina": other[field]})
    return {"status": "OHLCV_AGREE_ON_ACTIVE_SESSIONS" if not (missing or differences or halted_conflicts)
                        else "SOURCE_DISAGREEMENT_OR_INCOMPLETE", "active_sessions_compared": compared,
            "missing_active_sessions": missing, "differences": differences, "positive_volume_on_original_halts": halted_conflicts}


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ("raw-data-dir", "sina-data-dir", "feedback-replay-dir", "output"):
        parser.add_argument("--"+name, required=True)
    args = parser.parse_args(argv)
    raw_dir, sina_dir, replay, output = map(Path, (args.raw_data_dir,args.sina_data_dir,args.feedback_replay_dir,args.output))
    if output.exists(): raise ValueError("cross-provider audit output already exists")
    if sha256_file(raw_dir/"manifest.json") != EXPECTED_RAW_MANIFEST: raise ValueError("raw data identity changed")
    original = json.loads((raw_dir/"manifest.json").read_text())
    manifest = json.loads((sina_dir/"manifest.json").read_text())
    if (manifest["raw_manifest_sha256"] != EXPECTED_RAW_MANIFEST
            or manifest["codes"] != sorted(original["per_code_sha256"])
            or sha256_file(sina_dir/"plan.json") != manifest["plan_sha256"]):
        raise ValueError("source universe or capture plan identity changed")
    from scripts import capture_sina_daily_crosscheck as capture
    plan = json.loads((sina_dir/"plan.json").read_text())
    if (plan["capture_code_sha256"] != sha256_file(capture.__file__)
            or manifest["capture_code_sha256"] != plan["capture_code_sha256"]):
        raise ValueError("capture parser version changed")
    sources = {}; bars = {}; results = {}
    for code, expected in original["per_code_sha256"].items():
        raw_path = raw_dir/"codes"/(code+".json")
        if sha256_file(raw_path) != expected: raise ValueError("original source bytes changed")
        raw_packet = json.loads(raw_path.read_text()); bars[code] = {row["date"]:row for row in raw_packet["bars"]}
        path = sina_dir/"codes"/(code+".json")
        if code not in manifest["per_code_sha256"]:
            results[code] = {"status":"SOURCE_NOT_CAPTURED"}; continue
        if sha256_file(path) != manifest["per_code_sha256"][code]: raise ValueError("capture packet changed")
        packet = json.loads(path.read_text())
        if packet["instrument"] != code: raise ValueError("security capture identity changed")
        if packet["status"] != "BOUNDED_RESPONSE_CAPTURED":
            results[code] = {"status":packet["status"],"error":packet.get("error")}; continue
        if packet["raw_response_file"] != code+".response": raise ValueError("raw response filename changed")
        body = sina_dir/"codes"/packet["raw_response_file"]
        if sha256_file(body) != packet["raw_response_sha256"] or sha256_file(body) != manifest["raw_response_sha256"][code]:
            raise ValueError("raw HTTP response changed")
        rows, excluded = validate_sina_daily(json.loads(body.read_text(),parse_float=Decimal))
        if rows != packet["rows"] or excluded != packet["excluded_rows"]:
            raise ValueError("parsed daily rows contradict raw source")
        clock = [datetime.fromisoformat(packet[key]) for key in ("request_started_at","observed_at","completed_at")]
        if any(at.utcoffset() is None for at in clock) or clock != sorted(clock):
            raise ValueError("capture observation clock is not explicit/ordered")
        sources[code] = {row["day"]:row for row in rows}
        results[code] = compare_security(raw_packet["bars"],rows)
    expected_replay = "1c1ebd67e9d87ca4004b2d39b6c74aa8eb8f1ae20fdcfd4c23ece9f2eeb71006"
    if sha256_file(replay/"summary.json") != expected_replay: raise ValueError("fixed feedback replay changed")
    summary = json.loads((replay/"summary.json").read_text())
    opens = set(); closes = set(); carry = set()
    for bps, cases in summary["results_by_extra_bps_and_initial_CNY"].items():
        for capital, case in cases.items():
            if "artifact_sha256" not in case:
                if case["status"] != "INVALID_SINGLE_ORDER_LIMIT": raise ValueError("unexpected invalid case")
                continue
            folder = replay/bps/capital
            for name in ("fills.json","ownership.json"):
                if sha256_file(folder/name) != case["artifact_sha256"][name]: raise ValueError("replay source changed")
            for fill in json.loads((folder/"fills.json").read_text()):
                opens.add((fill["security_id"],fill["execution_at"][:10]))
            for day, owned in json.loads((folder/"ownership.json").read_text()).items():
                for code in owned:
                    (closes if bars[code][day]["tradestatus"]=="1" else carry).add((code,day))
    required = {}
    for field, keys in (("open",opens),("close",closes)):
        missing = []; different = []
        for code,day in sorted(keys):
            row = sources.get(code,{}).get(day)
            if row is None: missing.append([code,day]); continue
            if Decimal(row[field]) != Decimal(bars[code][day][field]): different.append([code,day])
        required[field] = {"unique_required_security_days":len(keys),"missing":missing,"different":different,
                           "exact_matches":len(keys)-len(missing)-len(different)}
    result = {"status":"ALL_FIXED_UNIVERSE_ACTIVE_OHLCV_AGREE" if all(r["status"]=="OHLCV_AGREE_ON_ACTIVE_SESSIONS" for r in results.values())
                        else "CROSS_PROVIDER_DISAGREEMENT_OR_INCOMPLETE",
              "raw_manifest_sha256":EXPECTED_RAW_MANIFEST,"sina_manifest_sha256":sha256_file(sina_dir/"manifest.json"),
              "feedback_summary_sha256":expected_replay,"audit_code_sha256":sha256_file(__file__),
              "securities":len(results),"active_sessions_compared":sum(r.get("active_sessions_compared",0) for r in results.values()),
              "per_security":results,"required_execution_and_valuation_prices":required,
              "known_halt_carry_security_days_not_certified_as_traded_closes":len(carry),
              "provider_upstream_independence_verified":False,"response_security_identity_certified":False,
              "original_prices_replaced":False,"historical_arrival_verified":False,
              "auction_execution_verified":False,"objective_achieved":False}
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({key:value for key,value in result.items() if key!="per_security"},indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
