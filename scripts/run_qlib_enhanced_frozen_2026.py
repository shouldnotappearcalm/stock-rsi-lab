"""Run the frozen enhanced-indexing candidate on the consumed 2026 interval once."""
import argparse
import hashlib
import json
import math
from pathlib import Path


START = "2026-01-05"
END = "2026-10-13"
RISK_END = "2026-10-12"
EXPECTED_PREDICTION_SHA256 = "551e80261ff20d426f7dcfb866e054a1a93c624737eb29efe7eb373f1eeb812d"
FROZEN_ECONOMIC_METHOD_COMMIT = "feb2d5925d7dd19a1d6b333cb077b527806a5a4d"
OPTIMIZER = {"lamb": 1.0, "delta": 0.2, "b_dev": 0.02}


def verify_frozen_inputs(prediction, risk_model_root, expected_sha256=EXPECTED_PREDICTION_SHA256,
                         start=START, end=END):
    path = Path(prediction)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("frozen 2026 prediction artifact hash mismatch")
    if (start, end) != (START, END):
        raise ValueError("diagnostic interval is fixed")
    risk_dates = sorted(item.name for item in Path(risk_model_root).iterdir()
                        if item.is_dir() and item.name.isdigit())
    if not risk_dates or risk_dates[-1] != RISK_END.replace("-", ""):
        raise ValueError("risk snapshots must end on the last pre-trade date")
    return hashlib.sha256(path.read_bytes()).hexdigest(), risk_dates[0], risk_dates[-1]


def summarize(report):
    net = (1 + report["return"] - report["cost"]).prod() - 1
    benchmark = (1 + report["bench"]).prod() - 1
    observations = len(report) - 1
    account = report.account
    values = {
        "sessions": len(report), "start": report.index.min().strftime("%Y-%m-%d"),
        "end": report.index.max().strftime("%Y-%m-%d"),
        "net_compound_return_pct": float(net * 100),
        "net_annualized_pct": float(((1 + net) ** (242 / observations) - 1) * 100),
        "benchmark_compound_return_pct": float(benchmark * 100),
        "compound_excess_pct": float((net - benchmark) * 100),
        "max_drawdown_pct": float((account / account.cummax() - 1).min() * 100),
        "average_exposure_pct": float((report.value.iloc[1:] / account.iloc[1:]).mean() * 100),
        "cost_pct_initial": float(report.total_cost.iloc[-1] / account.iloc[0] * 100),
        "turnover_x_initial": float(report.total_turnover.iloc[-1] / account.iloc[0]),
        "final_account": float(account.iloc[-1]),
    }
    if any(not math.isfinite(value) for value in values.values() if isinstance(value, float)):
        raise ValueError("finite diagnostic metrics required")
    return values


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--risk-model-root", required=True)
    parser.add_argument("--prediction", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    prediction_sha, risk_start, risk_end = verify_frozen_inputs(args.prediction, args.risk_model_root)

    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.evaluate import backtest_daily
    from stock_rsi.qlib_enhanced import pop_optimizer_audit_events

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=40)
    prediction = pd.read_pickle(args.prediction)
    dates = prediction.index.get_level_values("datetime")
    if dates.min().strftime("%Y-%m-%d") != START or dates.max().strftime("%Y-%m-%d") != END:
        raise ValueError("prediction dates do not match fixed diagnostic interval")
    pop_optimizer_audit_events()
    strategy = {
        "class": "WeeklyCachedEnhancedIndexingStrategy",
        "module_path": "stock_rsi.qlib_enhanced",
        "kwargs": {
            "signal": prediction, "riskmodel_root": args.risk_model_root,
            "market": "csi500", "risk_degree": 0.99,
            "cache_start": "2025-12-31", "cache_end": RISK_END,
            "latest_permitted_date": RISK_END, "optimizer_kwargs": OPTIMIZER,
        },
    }
    report, _ = backtest_daily(
        start_time=START, end_time=END, strategy=strategy,
        benchmark="SH000905", account=100_000_000,
        exchange_kwargs={
            "limit_threshold": 0.095, "deal_price": "close",
            "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5,
        },
    )
    audit = pop_optimizer_audit_events()
    if not audit or any(event["status"] != "optimal" for event in audit):
        raise RuntimeError("all diagnostic optimizations must be audited optimal")
    report_path = Path(args.report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_pickle(report_path)
    result = summarize(report)
    result.update({
        "status": "DIAGNOSTIC_ON_CONSUMED_2026_NOT_VALIDATION",
        "method_changed_after_open": False,
        "frozen_economic_method_commit": FROZEN_ECONOMIC_METHOD_COMMIT,
        "prediction_sha256": prediction_sha,
        "risk_snapshot_start": risk_start, "risk_snapshot_end": risk_end,
        "optimizer": OPTIMIZER, "risk_degree": 0.99,
        "optimizer_audit": {
            "solver": "CLARABEL", "solve_count": len(audit),
            "statuses": sorted(set(event["status"] for event in audit)),
            "max_constraint_violation": max(event["max_constraint_violation"] for event in audit),
            "constraint_relaxations": 0,
        },
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "target_net_return_pct": 20.0,
        "target_status": "PASS" if result["net_compound_return_pct"] >= 20 else "FAIL",
    })
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
