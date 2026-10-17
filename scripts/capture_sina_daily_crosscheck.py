"""Capture another provider's daily responses for the fixed research universe.

Evaluation only: never replace prices, drop securities or supply a decision
snapshot. This endpoint's response does not echo security identity; requests,
raw bytes, bounded parsing and unresolved coverage must stay explicit.
"""
import argparse
import json
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file
from scripts.capture_low_risk_raw_account_data import START, END, source_code


EXPECTED_RAW_MANIFEST = "4177efc8615eca4a53fec13161087ca9329b8f1448bc75a41e94179cb368f19a"
URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
FIELDS = ("open", "high", "low", "close", "volume")


def validate_sina_daily(payload):
    if not isinstance(payload, list) or not payload:
        raise ValueError("nonempty daily response required; null is not zero volume")
    rows = []; days = []; before = after = 0
    for raw in payload:
        if not isinstance(raw, dict) or not isinstance(raw.get("day"), str):
            raise ValueError("daily row/date schema changed")
        day = raw["day"]
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("canonical daily date required")
        values = {}
        for key in FIELDS:
            value = raw.get(key)
            if value is None or isinstance(value, bool):
                raise ValueError("missing or boolean daily numeric field")
            try:
                number = Decimal(str(value))
            except Exception as exc:
                raise ValueError("invalid daily numeric field") from exc
            if not number.is_finite() or number < 0:
                raise ValueError("negative or nonfinite daily numeric field")
            values[key] = number
        if values["volume"] != values["volume"].to_integral_value():
            raise ValueError("whole-share source volume required")
        if (values["high"] < max(values["open"], values["close"])
                or values["low"] > min(values["open"], values["close"])
                or values["volume"] > 0 and min(values[key] for key in FIELDS[:4]) <= 0):
            raise ValueError("invalid daily price bounds")
        days.append(day)
        if day < START: before += 1
        elif day > END: after += 1
        else: rows.append({"day": day, **{key: str(value) for key, value in values.items()}})
    if days != sorted(set(days)):
        raise ValueError("duplicate or unordered daily dates")
    if not rows:
        raise ValueError("response has no rows inside fixed validation window")
    return rows, {"before_window": before, "after_window": after}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-data-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    raw_dir, output = Path(args.raw_data_dir), Path(args.output_dir)
    if sha256_file(raw_dir/"manifest.json") != EXPECTED_RAW_MANIFEST:
        raise ValueError("fixed validation universe changed")
    original = json.loads((raw_dir/"manifest.json").read_text())
    codes = sorted(original["per_code_sha256"])
    symbols = {code: source_code(code).replace(".", "") for code in codes}
    plan = {"status": "FIXED_UNIVERSE_CROSS_PROVIDER_DAILY_CAPTURE", "capture_code_sha256": sha256_file(__file__),
            "raw_manifest_sha256": EXPECTED_RAW_MANIFEST, "codes": codes, "window": [START, END],
            "url": URL, "parameters": {"scale": 240, "ma": "no", "datalen": 1023},
            "response_echoes_security_identity": False, "historical_arrival_verified": False,
            "used_for_decision": False, "original_prices_replaced": False}
    if args.resume:
        if json.loads((output/"plan.json").read_text()) != plan:
            raise ValueError("cross-provider capture resume identity changed")
    else:
        if output.exists(): raise ValueError("cross-provider output already exists")
        (output/"codes").mkdir(parents=True)
        atomic_json(output/"plan.json", plan)
    import requests
    session = requests.Session(); consecutive_network_errors = 0
    for number, code in enumerate(codes, 1):
        packet_path = output/"codes"/(code+".json")
        if packet_path.exists():
            saved = json.loads(packet_path.read_text())
            if saved["instrument"] != code or saved["requested_symbol"] != symbols[code]:
                raise ValueError("saved security identity changed")
            if saved["status"] == "BOUNDED_RESPONSE_CAPTURED":
                body = output/"codes"/(code+".response")
                if sha256_file(body) != saved["raw_response_sha256"]:
                    raise ValueError("saved source response changed")
                rows, excluded = validate_sina_daily(json.loads(body.read_text(), parse_float=Decimal))
                if rows != saved["rows"] or excluded != saved["excluded_rows"]:
                    raise ValueError("saved parsed daily rows contradict raw response")
            continue
        body_path = output/"codes"/(code+".response")
        if body_path.exists(): raise ValueError("incomplete response checkpoint retained; do not overwrite")
        params = {**plan["parameters"], "symbol": symbols[code]}
        record = {"instrument": code, "requested_symbol": symbols[code], "source_url": URL,
                  "request_parameters": params, "request_started_at": datetime.now(timezone.utc).isoformat(),
                  "response_echoes_security_identity": False, "used_for_decision": False}
        try:
            response = session.get(URL, params=params, timeout=(10,20))
            record["observed_at"] = datetime.now(timezone.utc).isoformat()
            body_path.write_bytes(response.content)
            record.update(http_status=response.status_code, raw_response_sha256=sha256_file(body_path))
            response.raise_for_status()
            rows, excluded = validate_sina_daily(json.loads(response.text, parse_float=Decimal))
            record.update(status="BOUNDED_RESPONSE_CAPTURED", rows=rows, excluded_rows=excluded,
                          raw_response_file=body_path.name)
            consecutive_network_errors = 0
        except requests.RequestException as exc:
            record.update(status="HTTP_OR_NETWORK_ERROR", error=type(exc).__name__)
            consecutive_network_errors += 1
        except (ValueError, KeyError) as exc:
            record.update(status="INVALID_OR_UNAVAILABLE_SOURCE_RESPONSE", error=str(exc))
            consecutive_network_errors = 0
        record["completed_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(packet_path, record)
        if number % 10 == 0 or number == len(codes) or record["status"] != "BOUNDED_RESPONSE_CAPTURED":
            print(json.dumps({"attempted": number, "total": len(codes), "instrument": code,
                              "status": record["status"], "rows": len(record.get("rows", []))}), flush=True)
        if consecutive_network_errors >= 3:
            print("three consecutive network errors; remaining codes stay explicitly uncaptured", flush=True)
            break
        time.sleep(.2)
    hashes = {}; statuses = {}; body_hashes = {}
    for code in codes:
        path = output/"codes"/(code+".json")
        if not path.exists(): statuses[code] = "NOT_CAPTURED"; continue
        saved = json.loads(path.read_text()); hashes[code] = sha256_file(path); statuses[code] = saved["status"]
        if saved.get("raw_response_sha256"):
            body_path = output/"codes"/(code+".response")
            if sha256_file(body_path) != saved["raw_response_sha256"]: raise ValueError("source response bytes changed")
            body_hashes[code] = saved["raw_response_sha256"]
    manifest = {**plan, "status": "CROSS_PROVIDER_DAILY_CAPTURE_RECORDED", "plan_sha256": sha256_file(output/"plan.json"),
                "per_code_sha256": hashes, "raw_response_sha256": body_hashes, "status_by_code": statuses,
                "captured_codes": len(hashes), "bounded_responses": sum(value=="BOUNDED_RESPONSE_CAPTURED" for value in statuses.values())}
    atomic_json(output/"manifest.json", manifest)
    print(json.dumps({key: value for key, value in manifest.items() if key not in ("per_code_sha256", "raw_response_sha256", "status_by_code", "codes")}, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
