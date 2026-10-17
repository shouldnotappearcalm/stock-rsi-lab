"""Predeclared execution costs in a complete continuous fixed-target replay.

No alpha parameter is searched. Costs change cash, later target quantities,
fills and dividend entitlements. Actual opening auction/impact stay unverified.
"""
import argparse
import csv
import json
from functools import partial
from pathlib import Path

from scripts.capture_low_risk_raw_account_data import START, END, EXPECTED_TARGET_SHA256
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_low_risk_raw_share_validation import (
    CAPITALS, canonical_distributions, clean, simulate_fixed_targets, summarize_case, validate_source_coverage,
)
from stock_rsi.calendar import TradingCalendar
from stock_rsi.execution_cost import ExecutionCostBroker, SingleOrderLimitError
from stock_rsi.raw_share_account import RawShareAccount


EXTRA_BPS = (0, 5, 10, 20, 40)
PARENT_SUMMARY_SHA256 = "bbae8bdd56c20bf43e702cc45561e79131e650b4b4b2e60a1f25a98494bc7f83"
METHOD_FILES = (
    "scripts/run_low_risk_feedback_cost_stress.py", "scripts/run_low_risk_raw_share_validation.py",
    "scripts/capture_low_risk_raw_account_data.py", "scripts/capture_cninfo_csi500_reports_pre2026.py",
    "scripts/prepare_qlib_master_market_pre2026.py", "src/stock_rsi/raw_share_account.py",
    "src/stock_rsi/execution_cost.py", "src/stock_rsi/broker.py", "src/stock_rsi/models.py",
    "src/stock_rsi/data.py", "src/stock_rsi/calendar.py", "src/stock_rsi/time.py",
)


def profile_factory(extra_bps):
    if type(extra_bps) is not int or extra_bps not in EXTRA_BPS:
        raise ValueError("unregistered execution cost profile")
    return partial(RawShareAccount, broker_factory=partial(ExecutionCostBroker, extra_cost_bps=extra_bps))


def write_case(folder, case):
    with (folder/"daily.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(case["days"][0])); writer.writeheader(); writer.writerows(case["days"])
    for key in ("intents", "fills", "orders", "corporate_ledger", "ownership"):
        (folder/(key+".json")).write_text(json.dumps(clean(case[key]), indent=2)+"\n")
    return {path.name: sha256_file(path) for path in sorted(folder.iterdir())}


def require_zero_controls(controls):
    expected = {capital: "BYTE_EXACT_PARENT_REPRODUCED" for capital in CAPITALS[:-1]}
    expected[CAPITALS[-1]] = "REJECTED_KNOWN_OVERSIZED_PARENT_NOT_RETROACTIVELY_SPLIT"
    if controls != expected:
        raise RuntimeError("all registered zero-cost controls required before positive-cost outcomes")


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ("data-dir", "proof-dir", "targets", "parent-replay-dir", "plan", "expected-plan-sha256", "output-dir"):
        parser.add_argument("--"+name, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]; output = Path(args.output_dir)
    if output.exists(): raise ValueError("feedback-cost output already exists")
    if sha256_file(args.plan) != args.expected_plan_sha256: raise ValueError("feedback-cost plan changed")
    plan = json.loads(Path(args.plan).read_text())
    if (plan["status"] != "FROZEN_BEFORE_FEEDBACK_COST_OUTCOMES" or plan["capitals"] != list(CAPITALS)
            or plan["extra_cost_bps"] != list(EXTRA_BPS)
            or set(plan["method_code_sha256"]) != set(METHOD_FILES)
            or any(sha256_file(root/name) != value for name, value in plan["method_code_sha256"].items())
            or any(sha256_file(root/name) != value for name, value in plan["frozen_economic_core_sha256"].items())):
        raise ValueError("feedback-cost method or economic policy changed")
    if sha256_file(args.targets) != EXPECTED_TARGET_SHA256: raise ValueError("frozen target weights changed")
    data, proof_dir, parent = Path(args.data_dir), Path(args.proof_dir), Path(args.parent_replay_dir)
    if (sha256_file(data/"manifest.json") != plan["data_manifest_sha256"]
            or sha256_file(proof_dir/"manifest.json") != plan["proof_manifest_sha256"]
            or sha256_file(parent/"summary.json") != PARENT_SUMMARY_SHA256
            or plan["parent_summary_sha256"] != PARENT_SUMMARY_SHA256):
        raise ValueError("frozen source or parent identity changed")
    manifest = json.loads((data/"manifest.json").read_text())
    proof = json.loads((proof_dir/"manifest.json").read_text())
    previous = json.loads((parent/"summary.json").read_text())
    if manifest["window"] != [START, END]: raise ValueError("historical data window changed")
    for document in proof["documents"]:
        name = document["file"]
        if Path(name).name != name or sha256_file(proof_dir/name) != document["sha256"]:
            raise ValueError("primary corporate notice changed")
    if sha256_file(data/"calendar.json") != manifest["calendar_sha256"]:
        raise ValueError("explicit exchange calendar changed")
    calendar = TradingCalendar(json.loads((data/"calendar.json").read_text())["sessions"])
    packets = {}
    for code, expected in manifest["per_code_sha256"].items():
        path = data/"codes"/(code+".json")
        if sha256_file(path) != expected: raise ValueError("raw market packet changed")
        packet = json.loads(path.read_text())
        if (packet["instrument"] != code
                or [row["date"] for row in packet["bars"]] != [day.isoformat() for day in calendar.days]):
            raise ValueError("historical security/session identity changed")
        packets[code] = packet
    validate_source_coverage(packets)
    events = canonical_distributions(packets, proof)
    bars = {code: {row["date"]: row for row in packet["bars"]} for code, packet in packets.items()}
    targets = json.loads(Path(args.targets).read_text())
    output.mkdir(parents=True); results = {}; zero_controls = {}
    for bps in EXTRA_BPS:
        by_capital = {}
        results[str(bps)] = by_capital
        for capital in CAPITALS:
            print(f"feedback-cost replay extra_bps={bps} capital={capital}", flush=True)
            folder = output/str(bps)/capital; folder.mkdir(parents=True)
            try:
                case = simulate_fixed_targets(calendar, bars, events, targets, capital, account_factory=profile_factory(bps))
                if len(case["intents"]) != 34: raise ValueError("all frozen monthly decisions required")
                artifacts = write_case(folder, case)
                if bps == 0:
                    original = previous["results_by_initial_CNY"][capital]["artifact_sha256"]
                    if artifacts != original:
                        raise RuntimeError("zero-cost control diverged from parent; stop before any positive-cost outcome")
                    zero_controls[capital] = "BYTE_EXACT_PARENT_REPRODUCED"
                values = summarize_case(case, capital)
                ret = values["2026_through_"+END]["net_compound_return_pct"]
                by_capital[capital] = {
                    "status": "DAILY_PROXY_ACCOUNT_RECONCILED" if not case["whole_day_volume_violations"] else "INVALID_OBSERVED_TAPE_CAPACITY",
                    **values, "extra_cost_bps": bps, "target_policy_account_feedback_resimulated": True,
                    "all_generated_orders_within_single_order_limit": True,
                    "numeric_conditions_met_at_interim_cutoff": values["2024_return_pct"]>0 and values["2025_return_pct"]>0 and ret>=10,
                    "artifact_sha256": artifacts,
                }
            except SingleOrderLimitError as exc:
                by_capital[capital] = {"status": "INVALID_SINGLE_ORDER_LIMIT", "error": str(exc), "extra_cost_bps": bps}
                (folder/"error.json").write_text(json.dumps(by_capital[capital], indent=2)+"\n")
                if bps == 0:
                    if capital != CAPITALS[-1]:
                        raise RuntimeError("unexpected small-capital zero-control order rejection") from exc
                    zero_controls[capital] = "REJECTED_KNOWN_OVERSIZED_PARENT_NOT_RETROACTIVELY_SPLIT"
            except (ValueError, KeyError) as exc:
                by_capital[capital] = {"status": "INVALID_ACCOUNT_OR_SOURCE", "error": str(exc), "extra_cost_bps": bps}
                (folder/"error.json").write_text(json.dumps(by_capital[capital], indent=2)+"\n")
                if bps == 0:
                    raise RuntimeError("zero-cost source/account control failed; no positive-cost replay authorized") from exc
            (output/"case_results.json").write_text(json.dumps(results, indent=2)+"\n")
        if bps == 0:
            require_zero_controls(zero_controls)
    result = {
        "status": "FIXED_POLICY_FULL_ACCOUNT_COST_FEEDBACK_DIAGNOSTIC", "results_by_extra_bps_and_initial_CNY": results,
        "zero_cost_parent_controls": zero_controls, "target_sha256": EXPECTED_TARGET_SHA256,
        "parent_summary_sha256": PARENT_SUMMARY_SHA256, "plan_sha256": args.expected_plan_sha256,
        "data_manifest_sha256": plan["data_manifest_sha256"], "proof_manifest_sha256": plan["proof_manifest_sha256"],
        "end": END, "complete_requested_October": False, "new_alpha_candidates": 0,
        "extra_cost_scope": "Additional per-fill cash charge beyond baseline minimum/side fees, rounded per fill. Changes affordability, later NAV, orders and entitlements; not calibrated market impact.",
        "execution": "Same daily-open and 9.5% reference-price proxy; orders above 1 million shares rejected, no implicit child-order splitting.",
        "opening_liquidity_and_impact_verified": False, "historical_observed_arrival_verified": False,
        "older_minute_source_mismatches_resolved": False, "actual_FIFO_tax_implemented": False,
        "original_research_gate_status": "REJECTED", "research_promoted": False,
        "sealed_evidence": False, "objective_achieved": False,
    }
    (output/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__": raise SystemExit(main())
