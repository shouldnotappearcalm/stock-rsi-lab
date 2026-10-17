"""Immutable raw-share validation inputs for the already-frozen low-risk policy.

The source supplies unadjusted CNY/share bars and separate distributions.
No signal is refitted and no Qlib price file is modified. Current metadata
must not be used to filter historical stocks. Capture timestamps do not
prove historical arrival timestamps.
"""
import argparse
import json
import socket
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file


START, END = "2023-12-29", "2026-10-16"
EXPECTED_TARGET_SHA256 = "2900729ad58c851764216093b26ca777eed9d4c6d1e75f528ae9bb26b9eecafb"
BAR_FIELDS = ("date","code","open","high","low","close","preclose","volume","amount","adjustflag","tradestatus","isST")
DIVIDEND_FIELDS = ("code","dividPreNoticeDate","dividAgmPumDate","dividPlanAnnounceDate","dividPlanDate",
                   "dividRegistDate","dividOperateDate","dividPayDate","dividStockMarketDate",
                   "dividCashPsBeforeTax","dividCashPsAfterTax","dividStocksPs","dividCashStock","dividReserveToStockPs")
ADJUST_FIELDS = ("code","dividOperateDate","foreAdjustFactor","backAdjustFactor","adjustFactor")


def source_code(instrument):
    if (len(instrument) != 8 or instrument[:2] not in ("SH","SZ") or not instrument[2:].isdigit()
            or not instrument.startswith(("SH600","SH601","SH603","SH605","SZ000","SZ001","SZ002","SZ003"))):
        raise ValueError("ordinary-board security identity required")
    return instrument[:2].lower()+"."+instrument[2:]


def numeric(value):
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("finite source numeric field required")
    return number


def validate_bars(instrument, fields, rows):
    if tuple(fields) != BAR_FIELDS:
        raise ValueError("unadjusted market schema changed")
    result = []
    for values in rows:
        if len(values) != len(fields):
            raise ValueError("raw bar column count changed")
        row = dict(zip(fields,values))
        if (row["code"] != source_code(instrument) or not START <= row["date"] <= END
                or date.fromisoformat(row["date"]).isoformat() != row["date"]
                or row["adjustflag"] != "3" or row["tradestatus"] not in ("0","1")
                or row["isST"] not in ("0","1")):
            raise ValueError("wrong security, date, adjustment or historical state")
        for key in ("open","high","low","close","preclose","volume","amount"):
            if row[key] and numeric(row[key]) < 0:
                raise ValueError("negative raw source amount")
        if row["tradestatus"] == "1":
            if any(not row[key] or numeric(row[key]) <= 0 for key in ("open","high","low","close","preclose","volume")):
                raise ValueError("trading bar lacks positive prices or share volume")
            if (numeric(row["high"]) < max(numeric(row["open"]),numeric(row["close"]))
                    or numeric(row["low"]) > min(numeric(row["open"]),numeric(row["close"]))):
                raise ValueError("raw OHLC bounds inconsistent")
        result.append(row)
    if len(result) != len({row["date"] for row in result}):
        raise ValueError("duplicate raw market date")
    return result


def validate_dividends(instrument, fields, rows, year):
    if tuple(fields) != DIVIDEND_FIELDS:
        raise ValueError("corporate distribution schema changed")
    result, quarantine = [], []
    identities = set()
    for values in rows:
        if len(values) != len(fields):
            raise ValueError("distribution column count changed")
        row = dict(zip(fields,values))
        if row["code"] != source_code(instrument):
            raise ValueError("wrong distribution security")
        at = row["dividOperateDate"]
        if not at:
            quarantine.append({"reason":"MISSING_OPERATE_DATE","record":row})
            continue
        if date.fromisoformat(at).isoformat() != at or int(at[:4]) != year:
            raise ValueError("distribution operation year changed")
        if at > END:
            quarantine.append({"reason":"AFTER_CAPTURE_CUTOFF","record":row})
            continue
        if at < START:
            quarantine.append({"reason":"BEFORE_CAPTURE_WINDOW","record":row})
            continue
        for key in ("dividCashPsBeforeTax","dividStocksPs","dividReserveToStockPs"):
            if row[key] and numeric(row[key]) < 0:
                raise ValueError("negative distribution ratio")
        identity = json.dumps(row,sort_keys=True)
        if identity in identities:
            raise ValueError("duplicate distribution record")
        identities.add(identity)
        result.append(row)
    return result, quarantine


def query_rows(response):
    if response.error_code != "0":
        raise RuntimeError("BaoStock capture failed: "+response.error_msg)
    rows = []
    while response.next():
        rows.append(response.get_row_data())
    if response.error_code != "0":
        raise RuntimeError("BaoStock capture row retrieval failed")
    return list(response.fields), rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets",required=True)
    parser.add_argument("--output-dir",required=True)
    parser.add_argument("--resume",action="store_true")
    args = parser.parse_args(argv)
    if sha256_file(args.targets) != EXPECTED_TARGET_SHA256:
        raise ValueError("frozen low-risk target artifact changed")
    targets = json.loads(Path(args.targets).read_text())
    codes = sorted({code for target in targets.values() for code in target["weights"]})
    for code in codes:
        source_code(code)
    output = Path(args.output_dir)
    if args.resume:
        plan = json.loads((output/"plan.json").read_text())
        if (plan["capture_code_sha256"] != sha256_file(__file__) or plan["codes"] != codes
                or plan["target_sha256"] != EXPECTED_TARGET_SHA256 or plan["window"] != [START,END]):
            raise ValueError("raw-account capture resume identity changed")
    else:
        if output.exists():
            raise ValueError("raw-account capture output already exists")
        (output/"codes").mkdir(parents=True)
        plan = {"status":"FROZEN_RAW_ACCOUNT_CAPTURE", "codes":codes,"window":[START,END],
                "target_sha256":EXPECTED_TARGET_SHA256,"capture_code_sha256":sha256_file(__file__),
                "market_adjustflag":"3", "distribution_year_type":"operate",
                "historical_observed_arrival_verified":False,"current_metadata_used_for_historical_selection":False}
        atomic_json(output/"plan.json",plan)
    import baostock as bs
    socket.setdefaulttimeout(20)
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError("raw-account source login failed")
    try:
        if not (output/"calendar.json").exists():
            fields, raw = query_rows(bs.query_trade_dates(start_date=START,end_date=END))
            if fields != ["calendar_date","is_trading_day"]:
                raise ValueError("exchange calendar schema changed")
            sessions = []
            for at,flag in raw:
                if not START <= at <= END or flag not in ("0","1"):
                    raise ValueError("calendar crossed capture window")
                if flag == "1": sessions.append(at)
            if sessions != sorted(set(sessions)) or sessions[-1] != END:
                raise ValueError("complete explicit latest-session calendar required")
            atomic_json(output/"calendar.json",{"fields":fields,"raw":raw,"sessions":sessions})
        for index, code in enumerate(codes,1):
            path = output/"codes"/(code+".json")
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["instrument"] != code or saved["window"] != [START,END]:
                    raise ValueError("raw-account security checkpoint changed")
                continue
            symbol = source_code(code)
            fields, raw = query_rows(bs.query_history_k_data_plus(symbol, ",".join(BAR_FIELDS),
                                     start_date=START,end_date=END,frequency="d",adjustflag="3"))
            bars = validate_bars(code,fields,raw)
            distributions, quarantine = [], []
            for year in (2024,2025,2026):
                df, dr = query_rows(bs.query_dividend_data(symbol,year=str(year),yearType="operate"))
                accepted, excluded = validate_dividends(code,df,dr,year)
                distributions.extend(accepted)
                quarantine.extend(excluded)
            af, ar = query_rows(bs.query_adjust_factor(symbol,start_date=START,end_date=END))
            if tuple(af) != ADJUST_FIELDS:
                raise ValueError("adjustment event schema changed")
            adjustments = [dict(zip(af,row)) for row in ar]
            if any(row["code"] != symbol or not START <= row["dividOperateDate"] <= END for row in adjustments):
                raise ValueError("adjustment event outside bounded security/window")
            basic_fields, basic_rows = query_rows(bs.query_stock_basic(code=symbol))
            if not basic_rows or any(dict(zip(basic_fields,row)).get("code") != symbol for row in basic_rows):
                raise ValueError("current identity metadata security mismatch")
            atomic_json(path,{"instrument":code,"window":[START,END],"market_fields":fields,"bars":bars,
                              "dividend_fields":list(DIVIDEND_FIELDS),"distributions":distributions,
                              "quarantine":quarantine,"adjustment_fields":af,"adjustments":adjustments,
                              "current_basic_fields":basic_fields,"current_basic_rows":basic_rows,
                              "current_metadata_is_not_historical_status":True,
                              "observed_at":datetime.now(timezone.utc).isoformat()})
            print(json.dumps({"captured":index,"total":len(codes),"instrument":code,
                              "daily_rows":len(bars),"distributions":len(distributions)}),flush=True)
    finally:
        bs.logout()
    totals = {"bar_rows":0,"distribution_rows":0,"stock_distribution_rows":0,"adjustment_rows":0,"quarantined_rows":0}
    hashes = {}
    for code in codes:
        path = output/"codes"/(code+".json")
        saved = json.loads(path.read_text())
        hashes[code] = sha256_file(path)
        totals["bar_rows"] += len(saved["bars"])
        totals["distribution_rows"] += len(saved["distributions"])
        totals["adjustment_rows"] += len(saved["adjustments"])
        totals["quarantined_rows"] += len(saved["quarantine"])
        totals["stock_distribution_rows"] += sum(any(row[key] and numeric(row[key])>0 for key in
            ("dividStocksPs","dividReserveToStockPs")) for row in saved["distributions"])
    manifest = {"status":"RAW_ACCOUNT_VALIDATION_DATA_CAPTURED", "window":[START,END],
                "names":len(codes),"totals":totals,"source":"BaoStock unadjusted daily bars and separate corporate data",
                "source_units":{"price":"CNY per actual share","volume":"actual shares","amount":"CNY",
                                "dividCashPsBeforeTax":"CNY per actual entitled share"},
                "calendar_sha256":sha256_file(output/"calendar.json"),"plan_sha256":sha256_file(output/"plan.json"),
                "per_code_sha256":hashes,"target_sha256":EXPECTED_TARGET_SHA256,
                "capture_code_sha256":sha256_file(__file__),"provider_version":getattr(bs,"__version__",None),
                "policy_changed":False,"original_qlib_provider_modified":False,
                "historical_observed_arrival_verified":False,"data_completeness_guarantee":False}
    atomic_json(output/"manifest.json",manifest)
    print(json.dumps({key:value for key,value in manifest.items() if key != "per_code_sha256"},indent=2),flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
