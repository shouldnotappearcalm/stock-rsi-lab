"""Single user-goal diagnostic; do not relabel the failed research promotion gate.

The user requires profitable 2024/2025 and >=10% in 2026. This separate
diagnostic discloses the rejected relative-control gate, freezes the exact
candidate, and does not change any selection, weighting or execution rule.
"""
import argparse
import json
import math
import socket
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.capture_baostock_gap_states_pre2026 import FIELDS
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_cninfo_orj_signal_pre2026 import price_input_digest
from scripts.run_qlib_low_risk_pre2026 import (
    INITIAL_CASH, METHOD_FILES as PARENT_METHOD_FILES, OPEN_LIMITS, START,
    build_targets, load_state_capture, parse_memberships,
)
from scripts.run_qlib_roll1_frozen_2026 import calendar_year_metrics
from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.suspension_evidence import verify_suspension_mark


END, FIRST_2026 = "2026-10-13", "2026-01-05"
METHOD_FILES = (*PARENT_METHOD_FILES, "scripts/run_qlib_low_risk_goal_diagnostic_2026.py",
                "scripts/run_qlib_roll1_frozen_2026.py")
ECONOMIC_CORE = ("src/stock_rsi/low_risk_monthly.py", "src/stock_rsi/prior_close_orders.py",
                 "src/stock_rsi/qlib_prior_close.py")


def eligible_for_goal_diagnostic(summary):
    if (summary["status"] != "PRE2026_DEVELOPMENT_ONLY" or summary["end"] != "2025-12-31"
            or summary["candidate_budget"] != 1 or summary["2026_market_values_queried"] is not False):
        raise ValueError("completed pre-2026 evidence required")
    row = summary["results"]["low_vol36"]
    return (all(math.isfinite(row[key]) and row[key] > 0 for key in ("2024_return_pct","2025_return_pct"))
            and row["average_exposure_pct"] >= 90
            and row["unverified_held_marks"] == 0
            and row["all_monthly_decisions_match_prior_close_inventory_and_equity"] is True)


def validate_diagnostic_states(instrument, fields, rows):
    if tuple(fields) != FIELDS:
        raise ValueError("unexpected diagnostic historical state schema")
    code = instrument[:2].lower()+"."+instrument[2:]
    records = []
    for values in rows:
        if len(values) != len(FIELDS):
            raise ValueError("diagnostic state column count changed")
        row = dict(zip(fields,values))
        if (row["code"] != code or not "2023-12-29" <= row["date"] <= END
                or date.fromisoformat(row["date"]).isoformat() != row["date"]
                or row["tradestatus"] not in ("0","1") or row["isST"] not in ("0","1","")):
            raise ValueError("wrong security, date or state outside diagnostic cap")
        if row["close"] and (not math.isfinite(float(row["close"])) or float(row["close"]) <= 0):
            raise ValueError("invalid diagnostic source close")
        records.append(row)
    if len(records) != len({row["date"] for row in records}):
        raise ValueError("duplicate diagnostic historical date")
    return records


def full_input_hashes(provider):
    root = Path(provider)
    memberships = parse_memberships((root/"instruments/csi500.txt").read_text())
    codes = sorted(code for code,spans in memberships.items()
                   if any(first <= END and last >= "2023-12-29" for first,last in spans))
    return {"price_files":price_input_digest(root,codes),
            **{name:sha256_file(root/name) for name in (
                "instruments/csi500.txt","calendars/day.txt","features/sh000905/close.day.bin")}}


def extend_gap_states(snapshot, targets, states, output):
    first = {}
    for day, payload in sorted(targets.items()):
        for code in payload["weights"]:
            first.setdefault(code,day)
    gaps = {}
    for code, begin in first.items():
        missing = [day.isoformat() for day in snapshot.calendar
                   if max(FIRST_2026,begin) <= day.isoformat() <= END
                   and ((value:=snapshot.value(code,"close",day.isoformat())) is None or value <= 0)]
        if missing:
            gaps[code] = missing
    folder = output/"state_extension"
    folder.mkdir()
    (folder/"identified_gaps.json").write_text(json.dumps(gaps,indent=2)+"\n")
    if gaps:
        import baostock as bs
        socket.setdefaulttimeout(20)
        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError("diagnostic historical-state login failed")
        try:
            for code in sorted(gaps):
                first_query = FIRST_2026 if code in states else "2023-12-29"
                rs = bs.query_history_k_data_plus(code[:2].lower()+"."+code[2:], ",".join(FIELDS),
                                                   start_date=first_query,end_date=END,frequency="d",adjustflag="3")
                if rs.error_code != "0":
                    raise RuntimeError("diagnostic historical-state query failed: "+rs.error_msg)
                raw = []
                while rs.next():
                    raw.append(rs.get_row_data())
                if rs.error_code != "0":
                    raise RuntimeError("diagnostic historical-state row retrieval failed")
                records = validate_diagnostic_states(code,rs.fields,raw)
                current = states.setdefault(code,{})
                for row in records:
                    if row["date"] not in current:
                        current[row["date"]] = row
                (folder/(code+".json")).write_text(json.dumps({
                    "instrument":code,"query_window":[first_query,END],"fields":rs.fields,"rows":records,
                    "observed_at":datetime.now(timezone.utc).isoformat(),
                    "historical_observed_arrival_verified":False},indent=2)+"\n")
                print("diagnostic state captured "+code,flush=True)
        finally:
            bs.logout()
    manifest = {"source":"BaoStock historical state extension, adjustflag=3",
                "diagnostic_end":END,"gap_names":len(gaps),"original_price_provider_modified":False,
                "files_sha256":{p.name:sha256_file(p) for p in sorted(folder.iterdir())}}
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return states


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri",required=True)
    parser.add_argument("--development-dir",required=True)
    parser.add_argument("--pre2026-gap-states",required=True)
    parser.add_argument("--receipt",required=True)
    parser.add_argument("--expected-receipt-sha256",required=True)
    parser.add_argument("--output-dir",required=True)
    args = parser.parse_args(argv)
    output, development = Path(args.output_dir), Path(args.development_dir)
    if output.exists():
        raise ValueError("goal diagnostic output already exists")
    if sha256_file(args.receipt) != args.expected_receipt_sha256:
        raise ValueError("goal diagnostic receipt changed")
    receipt = json.loads(Path(args.receipt).read_text())
    root = Path(__file__).resolve().parents[1]
    if (receipt["status"] != "FROZEN_BEFORE_GOAL_2026_DIAGNOSTIC" or receipt["end"] != END
            or receipt["maximum_2026_diagnostics"] != 1
            or set(receipt["method_code_sha256"]) != set(METHOD_FILES)
            or any(sha256_file(root/name) != digest for name,digest in receipt["method_code_sha256"].items())):
        raise ValueError("goal diagnostic identity or method changed")
    parent_path = development/"summary.json"
    if sha256_file(parent_path) != receipt["parent_development_summary_sha256"]:
        raise ValueError("parent development result changed")
    parent = json.loads(parent_path.read_text())
    if not eligible_for_goal_diagnostic(parent):
        raise ValueError("user-required profitable development years not established")
    if parent["development_gate_status"] != receipt["original_research_gate_status"]:
        raise ValueError("original failed research gate must remain visible")
    for name in ECONOMIC_CORE:
        if sha256_file(root/name) != parent["method_code_sha256"][name]:
            raise ValueError("economic candidate changed after development")
    if full_input_hashes(args.provider_uri) != receipt["input_sha256"]:
        raise ValueError("diagnostic data snapshot changed")
    if (sha256_file(development/"targets.json") != parent["targets_sha256"]
            or sha256_file(development/"formation_receipts.json") != parent["formation_receipts_sha256"]):
        raise ValueError("parent formation or target evidence changed")
    states = load_state_capture(args.pre2026_gap_states,parent["gap_state_manifest_sha256"])
    output.mkdir(parents=True)
    (output/"opened.json").write_text(json.dumps(receipt,indent=2)+"\n")

    # First 2026 market values for this candidate are read only after preflight.
    snapshot = QlibSnapshot(args.provider_uri)
    memberships = parse_memberships((Path(args.provider_uri)/"instruments/csi500.txt").read_text())
    all_targets, formations = build_targets(snapshot,memberships,end=END,permitted_end=END)
    old_targets = json.loads((development/"targets.json").read_text())
    prefix = {name:{day:row for day,row in values.items() if day <= "2025-12-31"}
              for name,values in all_targets.items()}
    if prefix != old_targets:
        raise ValueError("2026 extension changed prior development targets")
    targets = all_targets["low_vol36"]
    (output/"targets.json").write_text(json.dumps(targets,indent=2)+"\n")
    (output/"formation_receipts.json").write_text(json.dumps(formations,indent=2)+"\n")
    states = extend_gap_states(snapshot,targets,states,output)

    import pandas as pd
    import qlib
    from qlib.backtest import backtest
    from qlib.constant import REG_CN
    from stock_rsi.qlib_prior_close import MonthlyPriorCloseStrategy
    qlib.init(provider_uri=args.provider_uri,region=REG_CN,kernels=1,logging_level=20)
    strategy = MonthlyPriorCloseStrategy(targets=targets,snapshot=snapshot)
    codes = sorted({code for row in targets.values() for code in row["weights"]})
    portfolio, indicators = backtest(
        start_time=START,end_time=END,strategy=strategy,benchmark="SH000905",account=INITIAL_CASH,
        executor={"class":"SimulatorExecutor","module_path":"qlib.backtest.executor",
                  "kwargs":{"time_per_step":"day","generate_portfolio_metrics":True}},
        exchange_kwargs={"freq":"day","codes":codes,"start_time":"2023-12-29","end_time":END,
                         "limit_threshold":OPEN_LIMITS,"deal_price":"open",
                         "open_cost":.0005,"close_cost":.0015,"min_cost":5})
    report, positions = portfolio["1day"]
    calendar = tuple(day for day in snapshot.calendar if day.isoformat() <= END)
    expected = pd.DatetimeIndex([day for day in calendar if START <= day.isoformat() <= END])
    if (not report.index.equals(expected) or len(strategy.intents) != 34
            or strategy.decision_days != [day.strftime("%Y-%m-%d") for day in expected]):
        raise ValueError("complete account calendar and all 34 monthly decisions required")
    for intention in strategy.intents:
        prior = date.fromisoformat(intention["as_of_close_convention"][:10])
        equity = float(report.loc[pd.Timestamp(prior),"account"]) if prior.isoformat() >= START else float(INITIAL_CASH)
        holdings = positions[pd.Timestamp(prior)].get_stock_amount_dict() if prior.isoformat() >= START else {}
        actual = intention["holdings_at_decision"]
        if (not math.isclose(intention["equity_at_decision"],equity,rel_tol=1e-10,abs_tol=.01)
                or set(actual) != set(holdings)
                or any(not math.isclose(actual[code],float(amount),rel_tol=1e-10,abs_tol=1e-8) for code,amount in holdings.items())):
            raise ValueError("diagnostic decision account crossed prior close")
    parent_report = development/"low_vol36/report.pkl"
    if sha256_file(parent_report) != parent["results"]["low_vol36"]["artifact_sha256"]["report.pkl"]:
        raise ValueError("parent account report changed")
    pd.testing.assert_frame_equal(report.loc[:"2025-12-31"],pd.read_pickle(parent_report),
                                  check_exact=False,atol=1e-5,rtol=1e-9)
    evidence = reconcile_daily_evidence(report,positions,indicators["1day"][1].order_indicator_his,
                                         calendar,initial_cash=INITIAL_CASH,
                                         signal_days={date.fromisoformat(row["as_of"]) for row in targets.values()})
    audits = []
    for row in evidence["holdings"]:
        value = snapshot.value(row["instrument"],"close",row["session"])
        if value is None or value <= 0:
            audits.append(verify_suspension_mark(snapshot,row["instrument"],row["session"],
                                                row["normalized_price"],states.get(row["instrument"],{})))
    report.to_pickle(output/"report.pkl")
    pd.to_pickle(positions,output/"positions.pkl")
    for key in ("days","orders","holdings"):
        pd.DataFrame(evidence[key]).to_csv(output/(key+".csv"),index=False)
    (output/"decision_intents.json").write_text(json.dumps(strategy.intents,indent=2)+"\n")
    (output/"suspension_mark_audit.json").write_text(json.dumps(audits,indent=2)+"\n")
    metrics = calendar_year_metrics(report,"2026")
    unexplained = sum(not row["verified"] for row in audits)
    result = {
        "status":"FIXED_USER_GOAL_DIAGNOSTIC_ON_CONSUMED_2026", "candidate":"low_vol36",
        "2024_return_pct":parent["results"]["low_vol36"]["2024_return_pct"],
        "2025_return_pct":parent["results"]["low_vol36"]["2025_return_pct"],"2026":metrics,
        "original_research_gate_status":parent["development_gate_status"],"research_promoted":False,
        "numeric_user_conditions_met_at_available_cutoff":metrics["net_compound_return_pct"] >= 10,
        "unverified_held_marks":unexplained,"verified_suspension_marks":len(audits)-unexplained,
        "requested_complete_October_covered":False,"strict_investment_claim_verified":False,
        "objective_achieved":False,"goal_receipt_sha256":args.expected_receipt_sha256,
        "monthly_decisions":len(strategy.intents),"total_sessions":len(report),"orders":len(evidence["orders"]),
        "unfilled_orders":sum(row["fill_status"] == "UNFILLED" for row in evidence["orders"]),
        "original_2024_2025_account_reproduced":True,"rule_changed_after_2026_open":False,
        "2026_feedback_to_new_variants":False,"claim_status":"CONSUMED_DIAGNOSTIC_NOT_FORMAL_PROMOTION_NOT_FULL_PIT",
        "artifact_sha256":{p.name:sha256_file(p) for p in sorted(output.iterdir()) if p.is_file()},
        "state_extension_manifest_sha256":sha256_file(output/"state_extension/manifest.json"),
    }
    (output/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2),flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
