"""One fixed Qlib rolling Ridge model with a 20-session return target.

The method comes from Qlib's RR[Linear] dynamic benchmark. The windows and
portfolio are reused from our frozen rolling LightGBM control. Ridge fits
both training and recent validation observations, all with mature labels.
"""
import argparse
import json
from pathlib import Path

from scripts.run_qlib_rolling20_pre2026 import (
    START, TEST_END, TEST_START, PERMITTED_END, LABEL, STEP,
    TRAIN_SESSIONS, VALID_SESSIONS, LABEL_LOOKAHEAD, digest, summarize, windows,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")

    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.evaluate import backtest_daily
    from qlib.contrib.model.linear import LinearModel
    from qlib.data import D
    from qlib.data.dataset import DatasetH

    output.mkdir(parents=True)
    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    receipts = list(windows(D.calendar(start_time=START, end_time=PERMITTED_END)))
    handler = Alpha158(
        start_time=START, end_time=TEST_END,
        fit_start_time=START, fit_end_time="2021-11-30",
        instruments="csi500", label=[LABEL],
        infer_processors=[
            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
        ],
        learn_processors=[
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
        ],
    )
    predictions = []
    for number, receipt in enumerate(receipts, 1):
        print(f"rolling ridge fit {number}/{len(receipts)} {receipt['test']}", flush=True)
        dataset = DatasetH(handler=handler, segments={key: receipt[key] for key in ("train", "valid", "test")})
        model = LinearModel(estimator="ridge", alpha=0.05, include_valid=True)
        model.fit(dataset)
        prediction = model.predict(dataset, segment="test")
        if isinstance(prediction, pd.DataFrame):
            prediction = prediction.iloc[:, 0]
        predictions.append(prediction)
    score = pd.concat(predictions).sort_index()
    if score.index.has_duplicates or score.index.get_level_values("datetime").max() > pd.Timestamp(TEST_END):
        raise ValueError("rolling prediction intervals overlap or exceed development end")
    pred_path = output / "pred.pkl"
    score.to_frame("score").to_pickle(pred_path)
    report, _ = backtest_daily(
        start_time=TEST_START, end_time=TEST_END,
        strategy={
            "class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy",
            "kwargs": {"signal": score.to_frame("score"), "topk": 100, "n_drop": 5, "risk_degree": 0.95},
        },
        benchmark="SH000905", account=100_000_000,
        exchange_kwargs={
            "limit_threshold": 0.095, "deal_price": "close",
            "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5,
        },
    )
    report_path = output / "report.pkl"
    report.to_pickle(report_path)
    result = {
        "status": "PRE2026_DEVELOPMENT_ONLY",
        "model": "Qlib RR[Linear] Ridge alpha=0.05 include_valid=True",
        "label": LABEL, "seed": 0,
        "candidate_budget": 1, "fit_count": len(receipts),
        "rolling_step_sessions": STEP, "train_sessions": TRAIN_SESSIONS,
        "valid_sessions": VALID_SESSIONS, "label_lookahead_sessions": LABEL_LOOKAHEAD,
        "portfolio": {"topk": 100, "n_drop": 5, "risk_degree": 0.95},
        "windows": receipts,
        "metrics": summarize(report),
        "prediction_sha256": digest(pred_path),
        "report_sha256": digest(report_path),
        "2026_market_data_accessed": False,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "windows"}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
