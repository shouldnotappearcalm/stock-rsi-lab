"""Bounded Qlib portfolio search over a pre-2026 development interval."""
import argparse
import json
import math
from pathlib import Path


CANDIDATES = (
    (30, 1), (30, 3), (30, 5),
    (50, 1), (50, 2), (50, 5), (50, 10),
    (100, 1), (100, 2), (100, 5), (100, 10),
    (150, 2), (150, 5), (200, 2), (200, 5),
)


def rank_candidates(rows):
    required = {
        "topk", "n_drop", "net_annualized_pct", "cost_pct_initial",
        "2024_return_pct", "2025_return_pct",
    }
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty candidate results required")
    checked = []
    for row in rows:
        if not isinstance(row, dict) or not required <= set(row):
            raise ValueError("incomplete candidate result")
        values = [row[key] for key in required if key not in {"topk", "n_drop"}]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in values):
            raise ValueError("finite candidate metrics required")
        if type(row["topk"]) is not int or type(row["n_drop"]) is not int or not 0 < row["n_drop"] <= row["topk"]:
            raise ValueError("valid topk/n_drop required")
        checked.append(dict(row))
    return sorted(
        checked,
        key=lambda row: (
            min(row["2024_return_pct"], row["2025_return_pct"]),
            row["net_annualized_pct"] - 0.1 * row["cost_pct_initial"],
            -row["topk"], -row["n_drop"],
        ),
        reverse=True,
    )


def _summary(report, topk, n_drop):
    net = (1 + report["return"] - report["cost"]).prod() - 1
    benchmark = (1 + report["bench"]).prod() - 1
    observations = len(report) - 1
    account = report["account"]
    row = {
        "topk": topk,
        "n_drop": n_drop,
        "net_compound_return_pct": float(net * 100),
        "net_annualized_pct": float(((1 + net) ** (242 / observations) - 1) * 100),
        "compound_excess_pct": float((net - benchmark) * 100),
        "max_drawdown_pct": float((account / account.cummax() - 1).min() * 100),
        "average_exposure_pct": float((report["value"].iloc[1:] / account.iloc[1:]).mean() * 100),
        "cost_pct_initial": float(report["total_cost"].iloc[-1] / account.iloc[0] * 100),
        "turnover_x_initial": float(report["total_turnover"].iloc[-1] / account.iloc[0]),
    }
    for year in ("2024", "2025"):
        frame = report.loc[year]
        row[f"{year}_return_pct"] = float(((1 + frame["return"] - frame["cost"]).prod() - 1) * 100)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--pred", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end", default="2025-12-30")
    args = parser.parse_args(argv)
    if args.start < "2024-01-01" or args.end >= "2026-01-01" or args.start > args.end:
        raise ValueError("research search is restricted to the registered 2024-2025 development interval")

    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.evaluate import backtest_daily

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=40)
    prediction = pd.read_pickle(args.pred)
    if prediction.index.get_level_values("datetime").max().strftime("%Y-%m-%d") >= "2026-01-01":
        raise ValueError("prediction artifact contains forbidden 2026 observations")
    rows = []
    for topk, n_drop in CANDIDATES:
        strategy = {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy",
            "kwargs": {"signal": prediction, "topk": topk, "n_drop": n_drop, "risk_degree": 0.95},
        }
        report, _ = backtest_daily(
            start_time=args.start,
            end_time=args.end,
            strategy=strategy,
            benchmark="SH000905",
            account=100000000,
            exchange_kwargs={
                "limit_threshold": 0.095,
                "deal_price": "close",
                "open_cost": 0.0005,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
        )
        rows.append(_summary(report, topk, n_drop))
    ranked = rank_candidates(rows)
    payload = {
        "selection_rule": "maximize worst calendar-year return, then annualized return net of cost penalty",
        "start": args.start,
        "end": args.end,
        "candidates": ranked,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"winner": ranked[0], "candidate_budget": len(ranked)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
