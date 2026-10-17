"""Post-evaluation checks of fixed orders; never supplies decision inputs."""
import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
from scripts.capture_low_risk_execution_tape import EXPECTED_SUMMARY, FIELDS, validate_minutes
from stock_rsi.broker import money


CENT = Decimal(".01")
STRESS_BPS = (5, 10, 20, 40)


def order_session(order):
    if not order.get("eligible_at"):
        return None
    at = datetime.fromisoformat(order["eligible_at"])
    if at.utcoffset() is None: raise ValueError("timezone-aware eligible order clock required")
    return order["security_id"], at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()


def validate_request_coverage(requests, capture_plan, minute_manifest, tapes):
    expected = sorted(set(requests))
    if (capture_plan["summary_sha256"] != EXPECTED_SUMMARY
            or capture_plan["requests"] != [list(key) for key in expected]
            or minute_manifest["requests"] != len(expected)
            or set(tapes) != set(expected)
            or len(minute_manifest["per_session_sha256"]) != len(expected)):
        raise ValueError("minute capture must cover the exact frozen order-session union")


def regular_main_board_limits(reference):
    """Arithmetic screen, not certification of the exchange's daily limit feed."""
    value = money(reference)
    if value <= 0 or value != value.quantize(CENT):
        raise ValueError("positive cent reference required for ordinary-board rule screen")
    upper = (value * Decimal("1.1")).quantize(CENT, rounding=ROUND_HALF_UP)
    lower = (value * Decimal(".9")).quantize(CENT, rounding=ROUND_HALF_UP)
    return max(CENT, min(value-CENT, lower)), max(value+CENT, upper)


def fixed_fill_cost_sensitivity(rows, fills, initial_cash):
    """No resimulation: original shares/dividends, cumulative extra cash charge.

    This cannot prove performance of the feedback policy with different costs.
    Any negative shadow cash is reported, never patched by removing a trade.
    """
    output = {}
    for bps in STRESS_BPS:
        charges = defaultdict(lambda: Decimal(0))
        # Round independently per fill, as a separate cash surcharge.
        for fill in fills:
            day = datetime.fromisoformat(fill["execution_at"]).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
            charges[day] += (money(fill["price"])*fill["quantity"]*bps/10000).quantize(CENT, rounding=ROUND_HALF_UP)
        cumulative = Decimal(0); nav = {}; negative_cash_days = 0
        for row in rows:
            cumulative += charges[row["day"]]
            nav[row["day"]] = money(row["equity"]) - cumulative
            negative_cash_days += money(row["cash"]) - cumulative < 0
        values = {"2024_pct": float((nav["2024-12-31"]/money(initial_cash)-1)*100),
                  "2025_pct": float((nav["2025-12-31"]/nav["2024-12-31"]-1)*100),
                  "2026_through_2026_10_16_pct": float((nav["2026-10-16"]/nav["2025-12-31"]-1)*100),
                  "additional_charge_CNY": str(cumulative), "negative_shadow_cash_days": negative_cash_days,
                  "same_target_policy_resimulated": False, "opening_fill_verified": False}
        output[str(bps)] = values
    return output


def audit_case(orders, fills, bars, tapes):
    oversized = [order for order in orders if order["quantity"] > 1000000]
    incomplete_orders = [order["order_id"] for order in orders if order_session(order) is not None
                         and len(tapes.get(order_session(order), [])) != 48]
    bad_limits = []; unknown_limits = []; unknown_tape = []; ratios = []; daily_mismatches = []
    for fill in fills:
        code = fill["security_id"]
        day = datetime.fromisoformat(fill["execution_at"]).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
        row = bars[code][day]; price = money(fill["price"])
        try:
            if not code.startswith(("SH600", "SH601", "SH603", "SH605", "SZ000", "SZ001", "SZ002", "SZ003")) or row["isST"] != "0":
                raise ValueError("unsupported board or historical ST state")
            lower, upper = regular_main_board_limits(row["preclose"])
            if not lower <= price <= upper:
                bad_limits.append(fill["order_id"])
        except ValueError:
            unknown_limits.append(fill["order_id"])
        tape = tapes.get((code, day))
        if not tape:
            unknown_tape.append(fill["order_id"]); continue
        # validate_minutes already checks all explicit labels and identities.
        if len(tape) != 48 or money(tape[0]["volume"]) <= 0:
            unknown_tape.append(fill["order_id"]); continue
        first = tape[0]
        aggregate = sum((money(item["volume"]) for item in tape), Decimal(0))
        if (aggregate != money(row["volume"]) or money(first["open"]) != money(row["open"])
                or money(tape[-1]["close"]) != money(row["close"])):
            daily_mismatches.append({"order_id": fill["order_id"], "instrument": code, "day": day,
                                     "minute_sum_volume": str(aggregate), "daily_volume": row["volume"],
                                     "first_open": first["open"], "daily_open": row["open"],
                                     "last_close": tape[-1]["close"], "daily_close": row["close"]})
        ratios.append({"order_id": fill["order_id"], "instrument": code, "day": day,
                       "quantity": fill["quantity"], "first_label_volume": first["volume"],
                       "fraction": Decimal(fill["quantity"])/money(first["volume"])})
    maximum = max(ratios, key=lambda item: item["fraction"]) if ratios else None
    status = ("INVALID_ORIGINAL_SINGLE_ORDER_TRACE" if oversized else
              "INVALID_REGULAR_BOARD_PRICE_SCREEN" if bad_limits else
              "INCOMPLETE_EXECUTION_SOURCE_CHECK" if unknown_limits or unknown_tape or daily_mismatches or incomplete_orders else
              "NECESSARY_SCREENS_PASSED_AUCTION_UNVERIFIED")
    return {"status": status, "orders_over_one_million_shares": len(oversized),
            "oversized_order_examples": oversized[:5], "filled_orders_over_one_million_shares": sum(f["quantity"]>1000000 for f in fills),
            "regular_board_limit_price_violations": bad_limits, "unknown_regular_board_limit_checks": unknown_limits,
            "incomplete_order_session_tape": incomplete_orders,
            "missing_or_incomplete_traded_tape": unknown_tape, "daily_minute_crosscheck_mismatches": daily_mismatches,
            "fills_checked": len(fills), "first_label_capacity": {
                "max_fraction": float(maximum["fraction"]) if maximum else None,
                "max_example": {key: float(value) if isinstance(value, Decimal) else value for key, value in maximum.items()} if maximum else None,
                "over_1pct": sum(item["fraction"]>Decimal(".01") for item in ratios),
                "over_5pct": sum(item["fraction"]>Decimal(".05") for item in ratios),
                "over_10pct": sum(item["fraction"]>Decimal(".1") for item in ratios),
                "over_100pct": sum(item["fraction"]>1 for item in ratios)},
            "auction_volume_inclusion_verified": False, "actual_exchange_limit_feed_verified": False,
            "opening_fill_verified": False, "policy_or_original_orders_changed": False}


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ("replay-dir", "raw-data-dir", "tape-dir", "plan", "expected-plan-sha256", "output"):
        parser.add_argument("--"+name, required=True)
    args = parser.parse_args(argv)
    replay, raw, tape, output = map(Path, (args.replay_dir, args.raw_data_dir, args.tape_dir, args.output))
    if output.exists(): raise ValueError("execution audit output already exists")
    if sha256_file(args.plan) != args.expected_plan_sha256: raise ValueError("registered execution plan changed")
    plan = json.loads(Path(args.plan).read_text()); root = Path(__file__).resolve().parents[1]
    if (plan["status"] != "FIXED_SIGNAL_POST_REPLAY_EXECUTION_AUDIT_REGISTERED"
            or plan["replay_summary_sha256"] != EXPECTED_SUMMARY
            or tuple(plan["additional_cost_bps_per_fill"]) != STRESS_BPS
            or any(sha256_file(root/name) != value for name, value in plan["code_sha256"].items())
            or any(sha256_file(root/name) != value for name, value in plan["frozen_source_dependency_sha256"].items())):
        raise ValueError("execution audit method changed")
    if (sha256_file(tape/"manifest.json") != plan["tape_manifest_sha256"]
            or sha256_file(raw/"manifest.json") != plan["raw_data_manifest_sha256"]
            or sha256_file(root/"experiments/qlib/low-risk-execution-rule-sources.json") != plan["rule_source_manifest_sha256"]):
        raise ValueError("execution source manifest changed")
    if sha256_file(replay/"summary.json") != EXPECTED_SUMMARY: raise ValueError("fixed replay changed")
    summary = json.loads((replay/"summary.json").read_text())
    manifest = json.loads((raw/"manifest.json").read_text())
    if sha256_file(raw/"manifest.json") != summary["data_manifest_sha256"]: raise ValueError("raw data identity changed")
    bars = {}
    for code, expected in manifest["per_code_sha256"].items():
        path = raw/"codes"/(code+".json")
        if sha256_file(path) != expected: raise ValueError("raw data bytes changed")
        bars[code] = {row["date"]: row for row in json.loads(path.read_text())["bars"]}
    minute = json.loads((tape/"manifest.json").read_text())
    if minute["summary_sha256"] != EXPECTED_SUMMARY: raise ValueError("minute tape belongs to another replay")
    if sha256_file(tape/"plan.json") != minute["plan_sha256"]: raise ValueError("minute capture plan changed")
    capture_plan = json.loads((tape/"plan.json").read_text())
    if (capture_plan["capture_code_sha256"] != minute["capture_code_sha256"]
            or capture_plan["capture_code_sha256"] != sha256_file(root/"scripts/capture_low_risk_execution_tape.py")
            or capture_plan["frequency_minutes"] != 5 or capture_plan["adjustflag"] != "3"
            or capture_plan["used_for_decision"] is not False):
        raise ValueError("minute capture method identity changed")
    tapes = {}
    row_count = complete_count = empty_count = 0
    for name, expected in minute["per_session_sha256"].items():
        path = tape/"sessions"/name
        if Path(name).name != name or sha256_file(path) != expected: raise ValueError("minute source bytes changed")
        packet = json.loads(path.read_text())
        rows, full = validate_minutes(packet["instrument"], packet["session"], packet["fields"],
                                     [[row[key] for key in FIELDS] for row in packet["rows"]])
        key = (packet["instrument"], packet["session"])
        if key in tapes: raise ValueError("duplicate minute identity")
        if name != key[0]+"-"+key[1]+".json" or packet["complete_48_slots"] != full:
            raise ValueError("minute filename or coverage declaration changed")
        row_count += len(rows); complete_count += full; empty_count += not rows
        tapes[key] = rows if full else []
    if (row_count != minute["minute_rows"] or complete_count != minute["complete_sessions"]
            or empty_count != minute["empty_sessions"]):
        raise ValueError("minute source count declaration changed")
    results = {}; orders_by_capital = {}; expected_requests = set()
    for capital, case in summary["results_by_initial_CNY"].items():
        path = replay/capital/"orders.json"
        if sha256_file(path) != case["artifact_sha256"]["orders.json"]: raise ValueError("order source changed")
        orders_by_capital[capital] = json.loads(path.read_text())
        expected_requests.update(key for order in orders_by_capital[capital] if (key := order_session(order)) is not None)
    validate_request_coverage(expected_requests, capture_plan, minute, tapes)
    if len(expected_requests) != plan["requested_code_sessions"] or row_count != plan["captured_minute_rows"]:
        raise ValueError("registered order-session coverage changed")
    for capital, case in summary["results_by_initial_CNY"].items():
        folder = replay/capital
        for name in ("orders.json", "fills.json", "daily.csv"):
            if sha256_file(folder/name) != case["artifact_sha256"][name]: raise ValueError("execution artifacts changed")
        orders = orders_by_capital[capital]; fills = json.loads((folder/"fills.json").read_text())
        with (folder/"daily.csv").open() as stream: daily = list(csv.DictReader(stream))
        results[capital] = {**audit_case(orders, fills, bars, tapes),
                            "fixed_fill_extra_cost_sensitivity_bps": fixed_fill_cost_sensitivity(daily, fills, capital)}
    result = {"status": "POST_REPLAY_EXECUTION_AUDIT", "replay_sha256": EXPECTED_SUMMARY,
              "registered_plan_sha256": args.expected_plan_sha256,
              "tape_manifest_sha256": sha256_file(tape/"manifest.json"), "code_sha256": sha256_file(__file__),
              "results_by_initial_CNY": results, "new_alpha_candidates": 0,
              "cost_sensitivity_scope": "Fixed fills only; cumulative extra charge, original shares and dividends. No feedback policy resimulation or impact model.",
              "regular_board_screen_scope": "Reconstructed 10% rounded limits for non-ST ordinary boards; no actual exchange daily limit feed or relisting-status certification.",
              "objective_achieved": False, "sealed_evidence": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
