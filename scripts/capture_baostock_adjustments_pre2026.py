"""Capture dated A-share adjustment events for the frozen CNINFO universe.

BaoStock is an optional research dependency. The output is event metadata,
never a return series or a portfolio decision. Completed per-code files are
immutable checkpoints; a resumed run verifies the exact frozen input plan.
"""
import argparse
import json
from pathlib import Path

from scripts.audit_cninfo_report_admission import END, START
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file


REQUIRED_FIELDS = ("code", "dividOperateDate", "foreAdjustFactor", "backAdjustFactor", "adjustFactor")


def baostock_code(instrument):
    if len(instrument) != 8 or instrument[:2] not in ("SH", "SZ") or not instrument[2:].isdigit():
        raise ValueError("invalid exchange-prefixed instrument")
    return instrument[:2].lower() + "." + instrument[2:]


def validate_rows(instrument, fields, rows):
    if tuple(fields) != REQUIRED_FIELDS:
        raise ValueError("unexpected BaoStock adjustment schema")
    expected = baostock_code(instrument)
    dated = []
    for row in rows:
        item = dict(zip(fields, row))
        if item["code"] != expected:
            raise ValueError("BaoStock returned the wrong security")
        day = item["dividOperateDate"]
        if not START <= day <= END:
            raise ValueError("adjustment crossed pre-2026 capture window")
        dated.append(item)
    if len(dated) != len({(row["dividOperateDate"], row["adjustFactor"]) for row in dated}):
        raise ValueError("duplicate adjustment event")
    return dated


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cninfo-plan", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    source = Path(args.cninfo_plan)
    output = Path(args.output_dir)
    cninfo_plan = json.loads(source.read_text())
    if cninfo_plan["window"] != [START, END]:
        raise ValueError("CNINFO plan is outside the registered pre-2026 window")
    codes = cninfo_plan["codes"]
    source_sha = sha256_file(source)

    if args.resume:
        if not (output / "plan.json").is_file():
            raise ValueError("resume requires an existing adjustment plan")
        plan = json.loads((output / "plan.json").read_text())
        if plan["codes"] != codes or plan["cninfo_plan_sha256"] != source_sha:
            raise ValueError("resume input differs from the frozen adjustment plan")
    else:
        if output.exists():
            raise ValueError("output directory already exists")
        plan = {"status": "FROZEN_ADJUSTMENT_CAPTURE_PLAN", "codes": codes,
                "window": [START, END], "cninfo_plan_sha256": source_sha,
                "source_api": "BaoStock query_adjust_factor"}
        (output / "codes").mkdir(parents=True)
        atomic_json(output / "plan.json", plan)

    import baostock as bs

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError("BaoStock login failed: " + login.error_msg)
    queried = 0
    try:
        for index, instrument in enumerate(codes, 1):
            path = output / "codes" / (instrument + ".json")
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["instrument"] != instrument or saved["window"] != [START, END]:
                    raise ValueError(f"invalid adjustment checkpoint: {instrument}")
            else:
                response = bs.query_adjust_factor(
                    code=baostock_code(instrument), start_date=START, end_date=END
                )
                if response.error_code != "0":
                    raise RuntimeError(f"BaoStock query failed for {instrument}: {response.error_msg}")
                rows = []
                while response.next():
                    rows.append(response.get_row_data())
                if response.error_code != "0":
                    raise RuntimeError(f"BaoStock row retrieval failed for {instrument}")
                events = validate_rows(instrument, response.fields, rows)
                atomic_json(path, {"instrument": instrument, "window": [START, END],
                                   "source_fields": response.fields, "events": events})
                queried += 1
            if index % 50 == 0 or index == len(codes):
                print(json.dumps({"completed": index, "total": len(codes),
                                  "queried_this_invocation": queried}), flush=True)
    finally:
        bs.logout()

    hashes = {}
    total = 0
    zero = 0
    for instrument in codes:
        path = output / "codes" / (instrument + ".json")
        if not path.is_file():
            raise ValueError(f"adjustment capture incomplete: {instrument}")
        saved = json.loads(path.read_text())
        validate_rows(instrument, saved["source_fields"], [list(event[field] for field in REQUIRED_FIELDS)
                                                         for event in saved["events"]])
        hashes[instrument] = sha256_file(path)
        total += len(saved["events"])
        zero += not saved["events"]
    result = {
        "status": "PRE2026_ADJUSTMENT_METADATA_CAPTURE_ONLY",
        "source": "BaoStock query_adjust_factor", "provider_version": getattr(bs, "__version__", None),
        "window": [START, END], "historical_names": len(codes),
        "adjustment_rows": total, "codes_without_rows": zero,
        "queried_this_invocation": queried,
        "cninfo_plan_sha256": source_sha,
        "plan_sha256": sha256_file(output / "plan.json"),
        "per_code_sha256": hashes,
        "data_completeness_guarantee": False,
        "2026_price_or_return_accessed": False,
        "investment_result": None,
    }
    atomic_json(output / "manifest.json", result)
    print(json.dumps({key: value for key, value in result.items() if key != "per_code_sha256"},
                     ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
