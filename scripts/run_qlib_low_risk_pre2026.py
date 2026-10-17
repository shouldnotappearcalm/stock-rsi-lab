"""One published low-risk hypothesis, with quantities fixed before next open.

Adaptation: CSI500 historical main-board members, CNY, equal weights instead
of the paper's MSCI universe/USD/value weights. No beta leverage or short leg.
"""
import argparse
import json
import math
from datetime import date
from pathlib import Path

from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_cninfo_orj_signal_pre2026 import price_input_digest
from scripts.capture_baostock_gap_states_pre2026 import FIELDS, validate_rows
from stock_rsi.low_risk_monthly import complete_month_ends, lowest_decile, monthly_volatility
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.suspension_evidence import verify_suspension_mark


START, END = "2024-01-02", "2025-12-31"
INITIAL_CASH = 100_000_000
OPEN_LIMITS = ("($open/Ref($close,1)-1)>=0.095", "($open/Ref($close,1)-1)<=-0.095")
METHOD_FILES = (
    "scripts/run_qlib_low_risk_pre2026.py", "src/stock_rsi/low_risk_monthly.py",
    "src/stock_rsi/prior_close_orders.py", "src/stock_rsi/qlib_prior_close.py",
    "src/stock_rsi/qlib_daily_evidence.py", "src/stock_rsi/qlib_snapshot.py",
    "src/stock_rsi/suspension_evidence.py", "scripts/capture_baostock_gap_states_pre2026.py",
)


def parse_memberships(text):
    result = {}
    for line in text.splitlines():
        symbol, first, last = line.split()
        if date.fromisoformat(first) > date.fromisoformat(last):
            raise ValueError("invalid historical membership interval")
        if symbol.startswith(("SH600", "SH601", "SH603", "SH605", "SZ000", "SZ001", "SZ002", "SZ003")):
            result.setdefault(symbol, []).append((first, last))
    return result


def members_on(memberships, day):
    return sorted(symbol for symbol, spans in memberships.items()
                  if any(first <= day <= last for first, last in spans))


def build_targets(snapshot, memberships, start=START, end=END, permitted_end=END):
    if start > end or end > permitted_end:
        raise ValueError("target generation exceeds the permitted research cap")
    targets = {"low_vol36": {}, "eligible_equal_weight": {}}
    receipts = []
    for index, day in enumerate(snapshot.calendar):
        if not start <= day.isoformat() <= end or index == 0:
            continue
        previous = snapshot.calendar[index - 1]
        if previous.strftime("%Y-%m") == day.strftime("%Y-%m"):
            continue
        endpoints = complete_month_ends(snapshot.calendar, previous)
        names = members_on(memberships, previous.isoformat())
        if len(names) < 200:
            raise ValueError("historical main-board universe unexpectedly small")
        view = AsOfPrices(snapshot, previous)
        scores = {}
        for symbol in names:
            volume = view.value(symbol, "volume", previous.isoformat())
            factor = view.value(symbol, "factor", previous.isoformat())
            if volume is None or factor is None or volume <= 0 or factor <= 0:
                continue
            value = monthly_volatility(view, symbol, endpoints)
            if value is not None:
                scores[symbol] = value
        if len(scores) < .8 * len(names):
            raise ValueError("36-month factor coverage below frozen 80% admission level")
        selected = lowest_decile(scores)
        for name, chosen in (("low_vol36", selected), ("eligible_equal_weight", sorted(scores))):
            targets[name][day.isoformat()] = {"as_of": previous.isoformat(),
                                             "weights": {symbol:.95 / len(chosen) for symbol in chosen}}
        receipts.append({"execution_session": day.isoformat(), "formation_asof": previous.isoformat(),
                         "first_month_end": endpoints[0].isoformat(), "monthly_returns": len(endpoints)-1,
                         "latest_factor_price_read": view.latest_read.isoformat(),
                         "historical_members": len(names), "eligible": len(scores),
                         "selected": list(selected), "scores": scores})
    return targets, receipts


def development_gate(candidate, control, *, missing_marks):
    keys = ("2024_return_pct", "2025_return_pct", "net_daily_volatility_annualized_pct", "average_exposure_pct")
    if any(not math.isfinite(row[key]) for row in (candidate, control) for key in keys):
        raise ValueError("finite complete development metrics required")
    return (missing_marks == 0 and candidate["2024_return_pct"] > 0 and candidate["2025_return_pct"] > 0
            and candidate["average_exposure_pct"] >= 90
            and min(candidate["2024_return_pct"], candidate["2025_return_pct"])
                > min(control["2024_return_pct"], control["2025_return_pct"])
            and candidate["net_daily_volatility_annualized_pct"] < control["net_daily_volatility_annualized_pct"])


def input_hashes(provider, memberships):
    root = Path(provider)
    codes = sorted(symbol for symbol, spans in memberships.items()
                   if any(first <= END and last >= "2023-12-29" for first, last in spans))
    return {"price_files": price_input_digest(root, codes),
            **{relative:sha256_file(root / relative) for relative in (
                "calendars/day.txt", "instruments/csi500.txt", "features/sh000905/close.day.bin")}}


def load_state_capture(directory, expected_manifest_sha):
    directory = Path(directory)
    if sha256_file(directory/"manifest.json") != expected_manifest_sha:
        raise ValueError("independent historical state manifest changed")
    manifest = json.loads((directory/"manifest.json").read_text())
    if (manifest["status"] != "PRE2026_INDEPENDENT_GAP_STATE_CAPTURE"
            or manifest["2026_market_values_queried"] is not False
            or manifest["window"] != ["2023-12-29",END]):
        raise ValueError("historical status capture crossed the pre-2026 boundary")
    records = {}
    for instrument, digest in manifest["per_code_sha256"].items():
        path = directory/"codes"/(instrument+".json")
        if sha256_file(path) != digest:
            raise ValueError("independent historical state file changed")
        saved = json.loads(path.read_text())
        if saved["instrument"] != instrument:
            raise ValueError("historical state security identity changed")
        rows = validate_rows(instrument,saved["fields"],[[row[key] for key in FIELDS] for row in saved["rows"]])
        records[instrument] = {row["date"]:row for row in rows}
    return records


def summarize(report):
    import pandas as pd
    net = report["return"] - report["cost"]
    value = float((1 + net).prod() - 1)
    if not math.isclose(value, float(report["account"].iloc[-1]) / INITIAL_CASH - 1, abs_tol=1e-9):
        raise ValueError("return and initial-cash equity do not reconcile")
    nav = pd.concat([pd.Series([float(INITIAL_CASH)]), report["account"].reset_index(drop=True)], ignore_index=True)
    result = {
        "sessions":len(report), "net_compound_return_pct":value*100,
        "net_annualized_pct":float(((1+value)**(242/len(report))-1)*100),
        "net_daily_volatility_annualized_pct":float(net.std(ddof=1)*math.sqrt(242)*100),
        "max_drawdown_pct":float((nav/nav.cummax()-1).min()*100),
        "average_exposure_pct":float((report["value"]/report["account"]).mean()*100),
        "cost_pct_initial":float(report["total_cost"].iloc[-1]/INITIAL_CASH*100),
        "turnover_x_initial":float(report["total_turnover"].iloc[-1]/INITIAL_CASH),
        "final_account":float(report["account"].iloc[-1]),
    }
    for year in ("2024", "2025"):
        part = net.loc[year]
        result[year+"_return_pct"] = float(((1+part).prod()-1)*100)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--gap-states")
    parser.add_argument("--plan", default=str(Path(__file__).resolve().parents[1]/"experiments/qlib/low-risk-pre2026-data-repair-plan.json"))
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")
    plan = json.loads(Path(args.plan).read_text())
    root = Path(__file__).resolve().parents[1]
    if (plan["status"] != "FROZEN_BEFORE_RESULTS" or set(plan["method_code_sha256"]) != set(METHOD_FILES)
            or any(sha256_file(root/name) != plan["method_code_sha256"][name] for name in METHOD_FILES)):
        raise ValueError("frozen campaign method source changed")
    memberships = parse_memberships((Path(args.provider_uri)/"instruments/csi500.txt").read_text())
    identities = input_hashes(args.provider_uri, memberships)
    if identities != plan["input_sha256"]:
        raise ValueError("frozen input snapshot changed")
    if not args.gap_states:
        raise ValueError("independent historical gap state capture required")
    states = load_state_capture(args.gap_states,plan["gap_state_manifest_sha256"])
    snapshot = QlibSnapshot(args.provider_uri)
    targets, receipts = build_targets(snapshot, memberships)
    if len(receipts) != 24:
        raise ValueError("all 24 monthly formation receipts required")
    output.mkdir(parents=True)
    (output/"targets.json").write_text(json.dumps(targets,indent=2)+"\n")
    (output/"formation_receipts.json").write_text(json.dumps(receipts,indent=2)+"\n")
    if (sha256_file(output/"targets.json") != plan["candidate_and_control_targets_must_reproduce_sha256"]
            or sha256_file(output/"formation_receipts.json") != plan["initial_formation_receipts_sha256"]):
        raise ValueError("data repair changed frozen formation evidence or target selection")
    print("frozen formation and target identities reproduced",flush=True)

    import pandas as pd
    import qlib
    from qlib.backtest import backtest
    from qlib.constant import REG_CN
    from stock_rsi.qlib_prior_close import MonthlyPriorCloseStrategy

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    calendar = tuple(day for day in snapshot.calendar if day.isoformat() <= END)
    expected = pd.DatetimeIndex([day for day in calendar if START <= day.isoformat() <= END])
    results, missing_total = {}, 0
    for name in ("eligible_equal_weight", "low_vol36"):
        print("monthly prior-close replay "+name, flush=True)
        strategy = MonthlyPriorCloseStrategy(targets=targets[name], snapshot=snapshot)
        codes = sorted({symbol for target in targets[name].values() for symbol in target["weights"]})
        portfolio, indicators = backtest(
            start_time=START, end_time=END, strategy=strategy,
            executor={"class":"SimulatorExecutor", "module_path":"qlib.backtest.executor",
                      "kwargs":{"time_per_step":"day", "generate_portfolio_metrics":True}},
            benchmark="SH000905", account=INITIAL_CASH,
            exchange_kwargs={"freq":"day", "codes":codes, "start_time":"2023-12-29",
                             "end_time":END, "limit_threshold":OPEN_LIMITS, "deal_price":"open",
                             "open_cost":.0005, "close_cost":.0015, "min_cost":5},
        )
        report, positions = portfolio["1day"]
        if not report.index.equals(expected) or strategy.decision_days != [day.strftime("%Y-%m-%d") for day in expected]:
            raise ValueError("account and decision calendar coverage incomplete")
        if len(strategy.intents) != 24:
            raise ValueError("monthly target decision count incomplete")
        for intention in strategy.intents:
            prior = date.fromisoformat(intention["as_of_close_convention"][:10])
            expected_equity = (float(report.loc[pd.Timestamp(prior),"account"])
                               if prior.isoformat() >= START else float(INITIAL_CASH))
            expected_holdings = (positions[pd.Timestamp(prior)].get_stock_amount_dict()
                                 if prior.isoformat() >= START else {})
            actual = intention["holdings_at_decision"]
            if (not math.isclose(intention["equity_at_decision"],expected_equity,rel_tol=1e-10,abs_tol=.01)
                    or set(actual) != set(expected_holdings)
                    or any(not math.isclose(actual[code],float(amount),rel_tol=1e-10,abs_tol=1e-8)
                           for code,amount in expected_holdings.items())):
                raise ValueError("decision inventory or equity crossed the prior-close boundary")
        evidence = reconcile_daily_evidence(report, positions, indicators["1day"][1].order_indicator_his,
                                             calendar, initial_cash=INITIAL_CASH,
                                             signal_days={date.fromisoformat(row["as_of"]) for row in targets[name].values()})
        mark_audit = []
        for row in evidence["holdings"]:
            quote = snapshot.value(row["instrument"],"close",row["session"])
            if quote is None or quote <= 0:
                mark_audit.append(verify_suspension_mark(snapshot,row["instrument"],row["session"],
                                                       row["normalized_price"],states.get(row["instrument"],{})))
        unexplained = sum(not row["verified"] for row in mark_audit)
        missing_total += unexplained
        branch = output/name
        branch.mkdir()
        report.to_pickle(branch/"report.pkl")
        pd.to_pickle(positions, branch/"positions.pkl")
        for key in ("days", "orders", "holdings"):
            pd.DataFrame(evidence[key]).to_csv(branch/(key+".csv"),index=False)
        (branch/"decision_intents.json").write_text(json.dumps(strategy.intents,indent=2)+"\n")
        (branch/"suspension_mark_audit.json").write_text(json.dumps(mark_audit,indent=2)+"\n")
        results[name] = summarize(report) | {
            "unverified_held_marks":unexplained,
            "missing_original_close_rows":len(mark_audit),
            "verified_suspension_marks":len(mark_audit)-unexplained, "orders":len(evidence["orders"]),
            "all_monthly_decisions_match_prior_close_inventory_and_equity":True,
            "unfilled_orders":sum(row["fill_status"] == "UNFILLED" for row in evidence["orders"]),
            "artifact_sha256":{p.name:sha256_file(p) for p in sorted(branch.iterdir())},
        }
    passed = development_gate(results["low_vol36"], results["eligible_equal_weight"], missing_marks=missing_total)
    result = {
        "status":"PRE2026_DEVELOPMENT_ONLY", "candidate_budget":1,
        "start":START, "end":END, "strategy":"monthly lowest decile of 36 monthly-return volatility",
        "universe":"historical CSI500 main-board constituents, 36 complete monthly returns, equal-weight CNY",
        "exposure_target":.95, "decision_clock":"one daily step; first session of month uses prior-close fixed quantities",
        "execution":"next-session open proxy; direction-specific 9.5% opening price-limit proxy",
        "development_gate_status":"PASS_LEAD_ONLY" if passed else "REJECTED",
        "development_gate":plan["development_gate"], "results":results,
        "input_sha256":identities, "plan_sha256":sha256_file(args.plan),
        "gap_state_manifest_sha256":plan["gap_state_manifest_sha256"],
        "method_code_sha256":plan["method_code_sha256"],
        "formation_receipts_sha256":sha256_file(output/"formation_receipts.json"),
        "targets_sha256":sha256_file(output/"targets.json"), "formation_months":len(receipts),
        "decision_boundary":"no execution-session quote or tradability query during order generation",
        "2026_market_values_queried":False, "2026_target_status":"NOT_EVALUATED",
        "claim_status":"REAL_PRICE_ENGINEERING_ONLY_NOT_SEALED_NOT_FULL_PIT",
        "remaining_execution_limits":["unverified legal ST limits and historical membership versions",
                                      "daily-bar suspension/first-trade price is not verified 09:30 auction data",
                                      "no queue, opening liquidity or market-impact model"],
    }
    (output/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2),flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
