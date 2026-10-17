"""One fixed monthly weak-overnight-trend avoidance module on frozen DE scores.

All economic parameters are frozen before outcomes. The paper's strongest
evidence concerns the short leg; this adaptation only deprioritizes its weak
decile within a long-only DE portfolio and retains the original turnover cap.
"""
import argparse
import json
from bisect import bisect_right
from pathlib import Path

from scripts.run_cninfo_orj_signal_pre2026 import price_input_digest
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_qlib_tra_pre2026 import summarize
from stock_rsi.overnight_trend import PastOnlyPrices, formation_window, overnight_trend, weakest_decile
from stock_rsi.qlib_snapshot import QlibSnapshot


START = "2024-01-02"
END = "2025-12-30"
PREDICTION_SHA256 = "98e3eb14736a41cc9369251b7c1e86532bc010d32a61ec22c76c0b710c9a108e"
PRICE_INPUT_SHA256 = "edfe02cf1b394d8b694ec0d3825231c57d1cfc1a194b292c3ae594d3a182f491"
QLIB_COMMIT = "54355232463878d2eebb91fe0ee5fa7fa1f5976c"
CONTROL_EXPECTED = {"net_annualized_pct": 27.134313367415185,
                    "2024_return_pct": 11.47273050374018, "2025_return_pct": 44.85253049460505}


def apply_monthly_avoidance(prediction, snapshot):
    import math
    import pandas as pd

    if list(prediction.index.names) != ["datetime", "instrument"] or prediction.index.has_duplicates:
        raise ValueError("unique datetime/instrument prediction index required")
    if prediction.index.get_level_values("datetime").max() >= pd.Timestamp("2026-01-01"):
        raise ValueError("2026 prediction cannot enter development")
    if not prediction.index.is_monotonic_increasing:
        raise ValueError("prediction must be ordered chronologically")
    filtered = prediction.copy()
    monthly = {}
    receipts = []
    for at, frame in prediction.groupby(level="datetime", sort=True):
        day = at.date()
        next_index = bisect_right(snapshot.calendar, day)
        if next_index >= len(snapshot.calendar):
            raise ValueError("missing next execution session")
        execution_day = snapshot.calendar[next_index]
        if execution_day.isoformat() > END:
            continue
        month = execution_day.strftime("%Y-%m")
        if month not in monthly:
            symbols = list(frame.index.get_level_values("instrument"))
            first, cutoff = formation_window(month)
            if cutoff >= day:
                raise ValueError("formation cutoff is not before decision time")
            view = PastOnlyPrices(snapshot, cutoff)
            scores = {}
            for symbol in symbols:
                value = overnight_trend(view, symbol, month)
                if value is not None:
                    scores[symbol] = value
            if len(scores) < 0.8 * len(symbols):
                raise ValueError(f"monthly factor coverage below 80%: {month}")
            monthly[month] = set(weakest_decile(scores))
            receipts.append({
                "execution_month": month, "decision_asof": str(at),
                "first_execution_day": execution_day.isoformat(),
                "formation_start": first.isoformat(), "formation_end": cutoff.isoformat(),
                "latest_price_read": view.latest_read.isoformat(),
                "universe_names": len(symbols), "scored_names": len(scores),
                "deprioritized": sorted(monthly[month]),
            })
        series = frame.iloc[:, 0]
        if not all(math.isfinite(value) for value in series):
            raise ValueError("finite DE scores required")
        minimum = float(series.min())
        floor = minimum - max(1.0, abs(minimum))
        for symbol in monthly[month]:
            key = (at, symbol)
            if key in filtered.index:
                filtered.loc[key, filtered.columns[0]] = floor
    return filtered, receipts


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--prediction", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")
    if PRICE_INPUT_SHA256.startswith("TO_BE_"):
        raise ValueError("price inputs must be frozen before outcome")
    if sha256_file(args.prediction) != PREDICTION_SHA256:
        raise ValueError("frozen DE prediction changed")

    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.evaluate import backtest_daily

    prediction = pd.read_pickle(args.prediction).loc[START:END]
    symbols = sorted(prediction.index.get_level_values("instrument").unique())
    if price_input_digest(args.provider_uri, symbols) != PRICE_INPUT_SHA256:
        raise ValueError("frozen overnight-factor price inputs changed")
    filtered, receipts = apply_monthly_avoidance(prediction, QlibSnapshot(args.provider_uri))
    output.mkdir(parents=True)
    filtered_path = output / "filtered_pred.pkl"
    filtered.to_pickle(filtered_path)
    (output / "formation_receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")
    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    results = {}
    for name, signal in (("de_control", prediction), ("weak_ovnt_avoidance", filtered)):
        report, _ = backtest_daily(
            start_time=START, end_time=END,
            strategy={"class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy",
                      "kwargs": {"signal": signal, "topk": 100, "n_drop": 2, "risk_degree": 0.95}},
            benchmark="SH000905", account=100_000_000,
            exchange_kwargs={"limit_threshold": 0.095, "deal_price": "close",
                             "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5},
        )
        path = output / (name + "_report.pkl")
        report.to_pickle(path)
        results[name] = summarize(report) | {"report_sha256": sha256_file(path)}
        if name == "de_control" and any(
                abs(results[name][key] - expected) > 1e-5 for key, expected in CONTROL_EXPECTED.items()):
            raise ValueError("DE control no longer reproduces the frozen baseline")
    control, candidate = results["de_control"], results["weak_ovnt_avoidance"]
    development_pass = (
        candidate["2024_return_pct"] > 0 and candidate["2025_return_pct"] > 0
        and candidate["average_exposure_pct"] >= 90
        and min(candidate["2024_return_pct"], candidate["2025_return_pct"])
            > min(control["2024_return_pct"], control["2025_return_pct"])
        and candidate["net_annualized_pct"] > control["net_annualized_pct"]
    )
    result = {
        "status": "PRE2026_DEVELOPMENT_ONLY", "candidate_budget": 1,
        "start": START, "end": END, "qlib_commit": QLIB_COMMIT,
        "module": "monthly bottom-decile adjusted overnight trend rank demotion; 12-2 convention",
        "portfolio": {"topk": 100, "n_drop": 2, "risk_degree": 0.95},
        "development_gate": "positive 2024/2025, >=90% average exposure, improve worst year and annualized vs DE",
        "development_gate_status": "PASS_LEAD_ONLY" if development_pass else "REJECTED",
        "user_target": {"2024_net_pct": ">0", "2025_net_pct": ">0", "2026_Jan_Oct_net_pct": ">=10"},
        "results": results,
        "prediction_sha256": PREDICTION_SHA256, "price_inputs_sha256": PRICE_INPUT_SHA256,
        "filtered_prediction_sha256": sha256_file(filtered_path),
        "formation_receipts_sha256": sha256_file(output / "formation_receipts.json"),
        "formation_months": len(receipts), "2026_market_values_queried": False,
        "2026_target_status": "NOT_EVALUATED", "claim_status": "DEVELOPMENT_ONLY_NOT_SEALED",
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
