"""One fixed 20-session rolling LightGBM experiment before 2026.

Qlib's dynamic benchmark retrains at a 20-session cadence to address concept
drift. This probe tests that adaptation separately from the already rejected
single-fit 20-session model. There is no parameter or portfolio search.
"""
import argparse
import hashlib
import json
from pathlib import Path


START = "2016-01-04"
TEST_START = "2024-01-02"
TEST_END = "2025-11-28"
PERMITTED_END = "2025-12-31"
LABEL = "Ref($close, -21) / Ref($close, -1) - 1"
LABEL_LOOKAHEAD = 21
STEP = 20
VALID_SESSIONS = 242
TRAIN_SESSIONS = 968


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def windows(calendar):
    """Yield train/validation/prediction dates with both label gaps purged."""
    import pandas as pd

    dates = pd.DatetimeIndex(calendar)
    start = dates.get_indexer([pd.Timestamp(TEST_START)])[0]
    end = dates.get_indexer([pd.Timestamp(TEST_END)])[0]
    if start < 0 or end < start or dates[-1] > pd.Timestamp(PERMITTED_END):
        raise ValueError("rolling calendar must stop inside 2025")
    if end + LABEL_LOOKAHEAD >= len(dates):
        raise ValueError("development labels would cross the permitted boundary")
    for index in range(start, end + 1, STEP):
        valid_end = index - LABEL_LOOKAHEAD - 1
        valid_start = valid_end - VALID_SESSIONS + 1
        train_end = valid_start - LABEL_LOOKAHEAD - 1
        train_start = train_end - TRAIN_SESSIONS + 1
        if train_start < 0:
            raise ValueError("insufficient historical sessions for rolling fit")
        test_end = min(index + STEP - 1, end)
        yield {
            "train": [dates[train_start].strftime("%Y-%m-%d"), dates[train_end].strftime("%Y-%m-%d")],
            "valid": [dates[valid_start].strftime("%Y-%m-%d"), dates[valid_end].strftime("%Y-%m-%d")],
            "test": [dates[index].strftime("%Y-%m-%d"), dates[test_end].strftime("%Y-%m-%d")],
            "valid_label_matures": dates[valid_end + LABEL_LOOKAHEAD].strftime("%Y-%m-%d"),
            "test_label_matures": dates[test_end + LABEL_LOOKAHEAD].strftime("%Y-%m-%d"),
        }


def summarize(report):
    net = (1 + report["return"] - report["cost"]).prod() - 1
    bench = (1 + report["bench"]).prod() - 1
    account = report["account"]
    result = {
        "sessions": len(report),
        "net_compound_return_pct": float(net * 100),
        "net_annualized_pct": float(((1 + net) ** (242 / (len(report) - 1)) - 1) * 100),
        "benchmark_compound_return_pct": float(bench * 100),
        "compound_excess_pct": float((net - bench) * 100),
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

    import numpy as np
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
    calendar = D.calendar(start_time=START, end_time=PERMITTED_END)
    receipts = list(windows(calendar))
    handler = Alpha158(
        start_time=START, end_time=TEST_END,
        fit_start_time=START, fit_end_time="2021-11-30",
        instruments="csi500", label=[LABEL],
    )
    predictions = []
    for number, receipt in enumerate(receipts, 1):
        print(f"rolling fit {number}/{len(receipts)} {receipt['test']}", flush=True)
        dataset = DatasetH(handler=handler, segments={key: receipt[key] for key in ("train", "valid", "test")})
        np.random.seed(0)
        model = LGBModel(
            loss="mse", colsample_bytree=0.8879, learning_rate=0.2,
            subsample=0.8789, lambda_l1=205.6999, lambda_l2=580.9768,
            max_depth=8, num_leaves=210, num_threads=8, seed=0,
        )
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
        "model": "Alpha158 LightGBM 20-session rolling refit",
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
