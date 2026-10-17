"""Append-only, pre-2026 historical status capture for identified Qlib gaps.

No provider price file is changed. These are reconstructed historical vendor
states, not a proof of historical observed delivery timestamps.
"""
import argparse
import json
import math
import socket
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file


START, END = "2023-12-29", "2025-12-31"
FIELDS = ("date", "code", "close", "tradestatus", "isST")


def validate_rows(instrument, fields, rows):
    if tuple(fields) != FIELDS:
        raise ValueError("unexpected historical status schema")
    code = instrument[:2].lower()+"."+instrument[2:]
    records = []
    for values in rows:
        if len(values) != len(FIELDS):
            raise ValueError("historical state column count changed")
        row = dict(zip(fields,values))
        if row["code"] != code or not START <= row["date"] <= END:
            raise ValueError("wrong security or state outside pre-2026 capture cap")
        if date.fromisoformat(row["date"]).isoformat() != row["date"] or row["tradestatus"] not in ("0","1"):
            raise ValueError("invalid date or historical tradestatus")
        if row["isST"] not in ("0","1",""):
            raise ValueError("invalid historical risk-warning state")
        if row["close"] and (not math.isfinite(float(row["close"])) or float(row["close"]) <= 0):
            raise ValueError("invalid reported source close")
        records.append(row)
    if len(records) != len({row["date"] for row in records}):
        raise ValueError("duplicate historical state date")
    return records


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-audit",required=True)
    parser.add_argument("--output-dir",required=True)
    parser.add_argument("--resume",action="store_true")
    args = parser.parse_args(argv)
    audit = json.loads(Path(args.price_audit).read_text())
    if audit["window"] != ["2024-01-02",END] or audit["2026_market_values_queried"] is not False:
        raise ValueError("pre-2026 missing-price audit required")
    codes = sorted(audit["missing"])
    output = Path(args.output_dir)
    if args.resume:
        plan = json.loads((output/"plan.json").read_text())
        if plan["price_audit_sha256"] != sha256_file(args.price_audit) or plan["codes"] != codes:
            raise ValueError("historical state resume plan changed")
        if plan["capture_code_sha256"] != sha256_file(__file__):
            raise ValueError("historical state capture implementation changed")
    else:
        if output.exists():
            raise ValueError("capture output already exists")
        plan = {"status":"FROZEN_HISTORICAL_STATE_CAPTURE", "codes":codes, "window":[START,END],
                "price_audit_sha256":sha256_file(args.price_audit), "fields":FIELDS,
                "capture_code_sha256":sha256_file(__file__),
                "purpose":"independent classification of gaps, never automatic price filling"}
        (output/"codes").mkdir(parents=True)
        atomic_json(output/"plan.json",plan)
    import baostock as bs
    socket.setdefaulttimeout(20)
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError("historical state login failed: "+login.error_msg)
    try:
        for index, instrument in enumerate(codes,1):
            path = output/"codes"/(instrument+".json")
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["instrument"] != instrument or saved["window"] != [START,END]:
                    raise ValueError("historical state checkpoint changed")
                validate_rows(instrument,saved["fields"],[[row[key] for key in FIELDS] for row in saved["rows"]])
                continue
            rs = bs.query_history_k_data_plus(instrument[:2].lower()+"."+instrument[2:], ",".join(FIELDS),
                                               start_date=START,end_date=END,frequency="d",adjustflag="3")
            if rs.error_code != "0":
                raise RuntimeError("historical state query failed: "+rs.error_msg)
            raw = []
            while rs.next():
                raw.append(rs.get_row_data())
            if rs.error_code != "0":
                raise RuntimeError("historical state row retrieval failed")
            rows = validate_rows(instrument,rs.fields,raw)
            atomic_json(path,{"instrument":instrument,"window":[START,END],"fields":rs.fields,
                              "rows":rows,"observed_at":datetime.now(timezone.utc).isoformat(),
                              "historical_observed_arrival_verified":False})
            print(json.dumps({"captured":index,"total":len(codes),"instrument":instrument,"rows":len(rows)}),flush=True)
    finally:
        bs.logout()
    hashes, coverage = {}, {"suspended":0,"trading":0,"missing":0}
    for instrument in codes:
        path = output/"codes"/(instrument+".json")
        saved = json.loads(path.read_text())
        states = {row["date"]:row["tradestatus"] for row in saved["rows"]}
        hashes[instrument] = sha256_file(path)
        for day in audit["missing"][instrument]:
            status = states.get(day)
            coverage["suspended" if status == "0" else "trading" if status == "1" else "missing"] += 1
    result = {"status":"PRE2026_INDEPENDENT_GAP_STATE_CAPTURE", "window":[START,END],
              "source":"BaoStock query_history_k_data_plus, adjustflag=3",
              "provider_version":getattr(bs,"__version__",None),"names":len(codes),
              "plan_sha256":sha256_file(output/"plan.json"),"price_audit_sha256":sha256_file(args.price_audit),
              "capture_code_sha256":sha256_file(__file__),
              "per_code_sha256":hashes,"gap_state_coverage":coverage,
              "2026_market_values_queried":False,"original_price_provider_modified":False,
              "historical_observed_arrival_verified":False}
    atomic_json(output/"manifest.json",result)
    print(json.dumps({key:value for key,value in result.items() if key != "per_code_sha256"},indent=2),flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
