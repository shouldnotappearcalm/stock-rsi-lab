"""Evaluate the saved first chronological TRA test pass without retraining."""
import argparse
import json
from pathlib import Path

from scripts.run_qlib_tra_pre2026 import (
    TEST_START, TEST_END, sha256_file as digest, first_pass_score, summarize,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--fit-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")
    fit_dir = Path(args.fit_dir) / "model"
    first_path = fit_dir / "test_pred.pkl"
    info_path = fit_dir / "info.json"
    model_path = fit_dir / "model.bin"
    if not all(path.is_file() for path in (first_path, info_path, model_path)):
        raise ValueError("TRA fit did not save a complete first-pass model and prediction")

    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.evaluate import backtest_daily

    first = first_pass_score(pd.read_pickle(first_path))
    output.mkdir(parents=True)
    pred_path = output / "pred.pkl"
    first.to_pickle(pred_path)
    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    report, _ = backtest_daily(
        start_time=TEST_START, end_time=TEST_END,
        strategy={
            "class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy",
            "kwargs": {"signal": first, "topk": 100, "n_drop": 2, "risk_degree": 0.95},
        },
        benchmark="SH000905", account=100_000_000,
        exchange_kwargs={
            "limit_threshold": 0.095, "deal_price": "close",
            "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5,
        },
    )
    report_path = output / "report.pkl"
    report.to_pickle(report_path)
    fit_info = json.loads(info_path.read_text())
    result = {
        "status": "PRE2026_DEVELOPMENT_ONLY",
        "signal": "TRA saved first chronological test pass",
        "start": TEST_START, "end": TEST_END,
        "training_budget": {
            "n_epochs": fit_info["config"]["n_epochs"],
            "early_stop": fit_info["config"]["early_stop"],
            "max_steps_per_epoch": fit_info["config"]["max_steps_per_epoch"],
            "seed": fit_info["config"]["seed"],
            "pretrain": fit_info["config"]["pretrain"],
        },
        "portfolio": {"topk": 100, "n_drop": 2, "risk_degree": 0.95},
        "metrics": summarize(report),
        "first_pass_raw_sha256": digest(first_path),
        "model_sha256": digest(model_path),
        "prediction_sha256": digest(pred_path),
        "report_sha256": digest(report_path),
        "2026_market_data_accessed": False,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
