"""Bounded pre-2026 search for the enhanced-indexing portfolio module."""
import argparse
import json
import math
from pathlib import Path


CANDIDATES = (
    {"lamb": 1.0, "delta": 0.2, "b_dev": 0.01},
    {"lamb": 0.25, "delta": 0.2, "b_dev": 0.01},
    {"lamb": 4.0, "delta": 0.2, "b_dev": 0.01},
    {"lamb": 1.0, "delta": 0.1, "b_dev": 0.01},
    {"lamb": 1.0, "delta": 0.3, "b_dev": 0.01},
    {"lamb": 1.0, "delta": 0.2, "b_dev": 0.02},
)
LATEST_DEVELOPMENT_DATE = "2025-12-30"


def validate_development_dates(start, end, cache_end):
    if start < "2024-01-01" or end > LATEST_DEVELOPMENT_DATE or start > end:
        raise ValueError("enhanced-indexing search is restricted to the 2024-2025 development interval")
    if cache_end > LATEST_DEVELOPMENT_DATE or cache_end < end:
        raise ValueError("cache_end must cover the run without reaching 2026")


def rank_candidates(rows):
    required = {
        "net_annualized_pct", "average_exposure_pct", "max_drawdown_pct",
        "turnover_x_initial", "2024_return_pct", "2025_return_pct",
    }
    checked = []
    for row in rows:
        if not isinstance(row, dict) or not required <= set(row):
            raise ValueError("incomplete candidate result")
        if any(isinstance(row[key], bool) or not isinstance(row[key], (int, float))
               or not math.isfinite(row[key]) for key in required):
            raise ValueError("finite candidate metrics required")
        checked.append(dict(row))
    eligible = [row for row in checked
                if row["net_annualized_pct"] >= 20 and row["average_exposure_pct"] >= 95]
    return sorted(eligible, key=lambda row: (
        min(row["2024_return_pct"], row["2025_return_pct"]),
        row["net_annualized_pct"], row["max_drawdown_pct"],
        -row["turnover_x_initial"],
    ), reverse=True)


def summarize(report, optimizer):
    net = (1 + report["return"] - report["cost"]).prod() - 1
    benchmark = (1 + report["bench"]).prod() - 1
    observations = len(report) - 1
    account = report.account
    row = {
        "optimizer": optimizer,
        "net_compound_return_pct": float(net * 100),
        "net_annualized_pct": float(((1 + net) ** (242 / observations) - 1) * 100),
        "benchmark_pct": float(benchmark * 100),
        "excess_pct": float((net - benchmark) * 100),
        "max_drawdown_pct": float((account / account.cummax() - 1).min() * 100),
        "average_exposure_pct": float((report.value.iloc[1:] / account.iloc[1:]).mean() * 100),
        "cost_pct_initial": float(report.total_cost.iloc[-1] / account.iloc[0] * 100),
        "turnover_x_initial": float(report.total_turnover.iloc[-1] / account.iloc[0]),
    }
    for year in ("2024", "2025"):
        frame = report.loc[year]
        row[f"{year}_return_pct"] = float(((1 + frame["return"] - frame["cost"]).prod() - 1) * 100)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--risk-model-root", required=True)
    parser.add_argument("--pred", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end", default=LATEST_DEVELOPMENT_DATE)
    parser.add_argument("--cache-start", default="2023-12-29")
    parser.add_argument("--cache-end", default=LATEST_DEVELOPMENT_DATE)
    args = parser.parse_args(argv)
    validate_development_dates(args.start, args.end, args.cache_end)

    risk_dates = [path.name for path in Path(args.risk_model_root).iterdir()
                  if path.is_dir() and path.name.isdigit()]
    if not risk_dates or max(risk_dates) >= "20260101":
        raise ValueError("risk model must be nonempty and capped before 2026")

    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.evaluate import backtest_daily
    from stock_rsi.qlib_enhanced import pop_optimizer_audit_events

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=40)
    prediction = pd.read_pickle(args.pred)
    maximum_prediction_date = prediction.index.get_level_values("datetime").max()
    if maximum_prediction_date >= pd.Timestamp("2026-01-01"):
        raise ValueError(f"prediction artifact contains forbidden 2026 observation: {maximum_prediction_date}")

    rows = []
    for number, optimizer in enumerate(CANDIDATES, 1):
        pop_optimizer_audit_events()
        strategy = {
            "class": "WeeklyCachedEnhancedIndexingStrategy",
            "module_path": "stock_rsi.qlib_enhanced",
            "kwargs": {
                "signal": prediction, "riskmodel_root": args.risk_model_root,
                "market": "csi500", "risk_degree": 0.99,
                "cache_start": args.cache_start, "cache_end": args.cache_end,
                "optimizer_kwargs": optimizer,
            },
        }
        try:
            report, _ = backtest_daily(
                start_time=args.start, end_time=args.end, strategy=strategy,
                benchmark="SH000905", account=100_000_000,
                exchange_kwargs={
                    "limit_threshold": 0.095, "deal_price": "close",
                    "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5,
                },
            )
        except RuntimeError as error:
            row = {
                "optimizer": optimizer, "candidate_number": number,
                "status": "FAILED_CONSTRAINTS", "error": str(error),
                "optimizer_audit": {
                    "solver": "CLARABEL", "constraint_relaxations": 0,
                    "completed_solve_count": len(pop_optimizer_audit_events()),
                },
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
            continue
        row = summarize(report, optimizer)
        audit_events = pop_optimizer_audit_events()
        if not audit_events:
            raise RuntimeError("optimizer emitted no audit events")
        row["optimizer_audit"] = {
            "solver": "CLARABEL",
            "solve_count": len(audit_events),
            "statuses": sorted(set(event["status"] for event in audit_events)),
            "max_constraint_violation": max(event["max_constraint_violation"] for event in audit_events),
            "max_realized_target_turnover": max(
                event["turnover"] for event in audit_events if event["turnover"] is not None
            ),
            "constraint_relaxations": 0,
        }
        row["candidate_number"] = number
        row["status"] = "COMPLETED"
        rows.append(row)
        print(json.dumps(row), flush=True)

    ranked = rank_candidates([row for row in rows if row["status"] == "COMPLETED"])
    payload = {
        "method": "weekly_cached_enhanced_indexing",
        "development_start": args.start,
        "development_end": args.end,
        "candidate_budget": len(CANDIDATES),
        "eligibility": {"net_annualized_pct_min": 20, "average_exposure_pct_min": 95},
        "selection_rule": "maximize worst calendar-year net return, then annualized net return, shallower drawdown, lower turnover",
        "candidates": rows,
        "winner": ranked[0] if ranked else None,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"winner": payload["winner"], "candidate_budget": len(CANDIDATES)}, indent=2))
    return 0 if ranked else 1


if __name__ == "__main__":
    raise SystemExit(main())
