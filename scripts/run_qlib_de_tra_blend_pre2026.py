"""One fixed pre-2026 test of complementary DoubleEnsemble and TRA signals.

No weights, dates, portfolio settings or candidates are selected after the
outcome is visible. The saved TRA prediction is its first chronological pass.
"""
import argparse
import json
from pathlib import Path

from scripts.run_qlib_tra_pre2026 import TEST_START, TEST_END, sha256_file, summarize


EXPECTED_FAST_SHA256 = "98e3eb14736a41cc9369251b7c1e86532bc010d32a61ec22c76c0b710c9a108e"
EXPECTED_TRA_SHA256 = "240ca8a2abd99022fcf73793017517547d58639a5a49937cfbb451a1bb1c5ef6"


def equal_rank_blend(fast, tra):
    import pandas as pd

    ranked = []
    for frame in (fast, tra):
        if not isinstance(frame, (pd.Series, pd.DataFrame)) or not isinstance(frame.index, pd.MultiIndex):
            raise ValueError("prediction requires datetime/instrument MultiIndex")
        if list(frame.index.names) != ["datetime", "instrument"] or frame.index.has_duplicates:
            raise ValueError("prediction index must be unique datetime/instrument pairs")
        dates = frame.index.get_level_values("datetime")
        if dates.max() >= pd.Timestamp("2026-01-01"):
            raise ValueError("post-2025 prediction is forbidden")
        series = frame.iloc[:, 0] if isinstance(frame, pd.DataFrame) else frame
        series = series.loc[TEST_START:TEST_END]
        ranked.append(series.groupby(level="datetime").rank(pct=True))
    pair = pd.concat(ranked, axis=1, join="inner").dropna()
    if pair.empty:
        raise ValueError("no shared predictions")
    pair.columns = ["fast", "tra"]
    coverage = pair.groupby(level="datetime").size()
    if coverage.min() < 100:
        raise ValueError("fewer than 100 shared names on a development session")
    if coverage.size != 482:
        raise ValueError("expected 482 daily prediction intersections")
    return ((pair.fast + pair.tra) / 2).to_frame("score"), {
        "sessions": int(coverage.size),
        "min_daily_shared_names": int(coverage.min()),
        "median_daily_shared_names": float(coverage.median()),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--fast-pred", required=True)
    parser.add_argument("--tra-pred", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")
    if sha256_file(args.fast_pred) != EXPECTED_FAST_SHA256:
        raise ValueError("DoubleEnsemble prediction hash mismatch")
    if sha256_file(args.tra_pred) != EXPECTED_TRA_SHA256:
        raise ValueError("TRA first-pass prediction hash mismatch")

    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.evaluate import backtest_daily

    fast = pd.read_pickle(args.fast_pred)
    tra = pd.read_pickle(args.tra_pred)
    blended, coverage = equal_rank_blend(fast, tra)
    fast_only = fast.loc[TEST_START:TEST_END]
    output.mkdir(parents=True)
    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    results = {}
    for name, signal in (("fast_only", fast_only), ("equal_rank_blend", blended)):
        report, _ = backtest_daily(
            start_time=TEST_START, end_time=TEST_END,
            strategy={
                "class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy",
                "kwargs": {"signal": signal, "topk": 100, "n_drop": 2, "risk_degree": 0.95},
            },
            benchmark="SH000905", account=100_000_000,
            exchange_kwargs={
                "limit_threshold": 0.095, "deal_price": "close",
                "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5,
            },
        )
        report_path = output / f"{name}_report.pkl"
        report.to_pickle(report_path)
        results[name] = summarize(report) | {"report_sha256": sha256_file(report_path)}
    pred_path = output / "blend_pred.pkl"
    blended.to_pickle(pred_path)
    result = {
        "status": "PRE2026_DEVELOPMENT_ONLY", "candidate_budget": 1,
        "method": "daily rank percentile, equal 50/50 DoubleEnsemble and first-pass TRA",
        "start": TEST_START, "end": TEST_END,
        "portfolio": {"topk": 100, "n_drop": 2, "risk_degree": 0.95},
        "coverage": coverage,
        "fast_prediction_sha256": EXPECTED_FAST_SHA256,
        "tra_prediction_sha256": EXPECTED_TRA_SHA256,
        "blend_prediction_sha256": sha256_file(pred_path),
        "results": results,
        "2026_market_data_accessed": False,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
