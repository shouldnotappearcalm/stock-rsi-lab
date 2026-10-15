"""One pre-2026 20-session label aligned to a Top100/Drop5 portfolio.

Qlib's dynamic benchmark documents a 20-session Alpha158 label. This probe
changes the prediction horizon, while keeping the official LightGBM model
parameters and Qlib's exchange assumptions fixed.
"""
import argparse
import hashlib
import json
from pathlib import Path


START = "2016-01-04"
TRAIN_END = "2021-11-30"
VALID_START = "2022-01-04"
VALID_END = "2023-11-30"
TEST_START = "2024-01-02"
TEST_END = "2025-11-28"
FINAL_PERMITTED_DATE = "2025-12-31"
LABEL = "Ref($close, -21) / Ref($close, -1) - 1"
HORIZON = 21


def validate_dates(train_end=TRAIN_END, valid_end=VALID_END, test_end=TEST_END):
    if not (START < train_end < VALID_START < valid_end < TEST_START < test_end < FINAL_PERMITTED_DATE):
        raise ValueError("20-session probe requires purged, pre-2026 splits")


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def summarize(report):
    net = (1 + report["return"] - report["cost"]).prod() - 1
    benchmark = (1 + report["bench"]).prod() - 1
    account = report["account"]
    result = {
        "sessions": len(report),
        "net_compound_return_pct": float(net * 100),
        "net_annualized_pct": float(((1 + net) ** (242 / (len(report) - 1)) - 1) * 100),
        "benchmark_compound_return_pct": float(benchmark * 100),
        "compound_excess_pct": float((net - benchmark) * 100),
        "max_drawdown_pct": float((account / account.cummax() - 1).min() * 100),
        "average_exposure_pct": float((report["value"].iloc[1:] / account.iloc[1:]).mean() * 100),
        "cost_pct_initial": float(report["total_cost"].iloc[-1] / account.iloc[0] * 100),
        "turnover_x_initial": float(report["total_turnover"].iloc[-1] / account.iloc[0]),
    }
    for year in ("2024", "2025"):
        part = report.loc[year]
        result[f"{year}_return_pct"] = float(((1 + part["return"] - part["cost"]).prod() - 1) * 100)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    validate_dates()

    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.evaluate import backtest_daily
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.data import D
    from qlib.data.dataset import DatasetH

    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")
    output.mkdir(parents=True)
    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    calendar = pd.DatetimeIndex(D.calendar(start_time=START, end_time=FINAL_PERMITTED_DATE))
    label_end_dates = {}
    for name, day in {"train": TRAIN_END, "valid": VALID_END, "test": TEST_END}.items():
        index = calendar.get_indexer([pd.Timestamp(day)])[0]
        if index < 0 or index + HORIZON >= len(calendar):
            raise ValueError(f"{name} label crosses the permitted calendar")
        label_end_dates[name] = calendar[index + HORIZON].strftime("%Y-%m-%d")

    handler = Alpha158(
        start_time=START, end_time=TEST_END,
        fit_start_time=START, fit_end_time=TRAIN_END,
        instruments="csi500", label=[LABEL],
    )
    segments = {
        "train": (START, TRAIN_END),
        "valid": (VALID_START, VALID_END),
        "test": (TEST_START, TEST_END),
    }
    dataset = DatasetH(handler=handler, segments=segments)
    model = LGBModel(
        loss="mse", colsample_bytree=0.8879, learning_rate=0.2,
        subsample=0.8789, lambda_l1=205.6999, lambda_l2=580.9768,
        max_depth=8, num_leaves=210, num_threads=8, seed=0,
    )
    model.fit(dataset)
    prediction = model.predict(dataset, segment="test")
    if isinstance(prediction, pd.DataFrame):
        prediction = prediction.iloc[:, 0]
    if prediction.index.get_level_values("datetime").max() > pd.Timestamp(TEST_END):
        raise ValueError("prediction exceeds the fixed development interval")
    prediction = prediction.to_frame("score")
    pred_path = output / "pred.pkl"
    prediction.to_pickle(pred_path)
    report, _ = backtest_daily(
        start_time=TEST_START, end_time=TEST_END,
        strategy={
            "class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy",
            "kwargs": {"signal": prediction, "topk": 100, "n_drop": 5, "risk_degree": 0.95},
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
        "hypothesis": "match next-session 20-session return target to roughly 20-session portfolio replacement",
        "qlib_dynamic_benchmark_label_horizon": 20,
        "label": LABEL,
        "splits": segments,
        "latest_label_input_dates": label_end_dates,
        "seed": 0, "candidate_budget": 1,
        "portfolio": {"topk": 100, "n_drop": 5, "risk_degree": 0.95},
        "metrics": summarize(report),
        "prediction_sha256": digest(pred_path),
        "report_sha256": digest(report_path),
        "2026_market_data_accessed": False,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
