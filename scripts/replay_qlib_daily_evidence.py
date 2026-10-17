"""Daily Qlib replay with holdings, order indicators and reconciled cash flows."""
import argparse
import json
from datetime import date
from pathlib import Path

from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence
from stock_rsi.qlib_snapshot import QlibSnapshot


def replay_with_evidence(signal, provider_uri, output, start, end):
    import pandas as pd
    import qlib
    from qlib.backtest import backtest
    from qlib.constant import REG_CN

    output = Path(output)
    if output.exists():
        raise ValueError("evidence output directory already exists")
    output.mkdir(parents=True)
    qlib.init(provider_uri=provider_uri, region=REG_CN, kernels=1, logging_level=20)
    portfolio, indicators = backtest(
        start_time=start, end_time=end,
        strategy={"class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy",
                  "kwargs": {"signal": signal, "topk": 100, "n_drop": 2, "risk_degree": 0.95}},
        executor={"class": "SimulatorExecutor", "module_path": "qlib.backtest.executor",
                  "kwargs": {"time_per_step": "day", "generate_portfolio_metrics": True}},
        benchmark="SH000905", account=100_000_000,
        exchange_kwargs={"freq": "day", "limit_threshold": 0.095, "deal_price": "close",
                         "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5},
    )
    report, positions = portfolio["1day"]
    calendar = tuple(day for day in QlibSnapshot(provider_uri).calendar if day <= date.fromisoformat(end))
    expected = pd.DatetimeIndex([day for day in calendar if start <= day.isoformat() <= end])
    if not report.index.equals(expected):
        raise ValueError("full requested account session coverage required")
    evidence = reconcile_daily_evidence(
        report, positions, indicators["1day"][1].order_indicator_his, calendar,
        initial_cash=100_000_000,
        signal_days=set(signal.index.get_level_values("datetime").date),
    )
    report.to_pickle(output / "report.pkl")
    pd.to_pickle(positions, output / "positions.pkl")
    for key in ("days", "orders", "holdings"):
        pd.DataFrame(evidence[key]).to_csv(output / (key + ".csv"), index=False)
    result = {
        "status": "RECONCILED_DAILY_ENGINEERING_REPLAY", "start": start, "end": end,
        "sessions": len(report), "order_rows": len(evidence["orders"]),
        "holdings_rows": len(evidence["holdings"]),
        "total_cost": evidence["total_cost"], "total_turnover": evidence["total_turnover"],
        "initial_cash": 100_000_000, "continuous_account": True,
        "signal_clock": "One daily close signal, previous explicit session's score used at next session close",
        "wake_frequency": "one daily decision step; training every 20 sessions when scheduled",
        "units": "Qlib normalized prices and amounts; monetary values in CNY",
        "asof_limit": "15:00+08:00 is a close-bar convention; historical observed arrival times are not verified",
        "execution_limit": "Daily price/limit proxies; no intraday queue, announcement stream or complete PIT proof",
        "artifact_sha256": {name: sha256_file(output / name) for name in (
            "report.pkl", "positions.pkl", "days.csv", "orders.csv", "holdings.csv")},
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return report, result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--prediction", required=True)
    parser.add_argument("--expected-prediction-sha256", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    if sha256_file(args.prediction) != args.expected_prediction_sha256:
        raise ValueError("replay prediction identity changed")
    import pandas as pd
    _, manifest = replay_with_evidence(pd.read_pickle(args.prediction), args.provider_uri,
                                      args.output_dir, args.start, args.end)
    print(json.dumps(manifest, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
