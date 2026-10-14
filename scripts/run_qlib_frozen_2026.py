"""Run the frozen pre-2026 Qlib model on the consumed 2026 replay interval."""
import argparse
import hashlib
import json
import math
import pickle
from pathlib import Path


START = "2026-01-05"
END = "2026-10-13"
EXPECTED_MODEL_SHA256 = "0ac63a71bc6777257ce18cef62340c2666065397d059a319af39653b93ba280f"


def verify_frozen_inputs(model_path, expected_sha256, start=START, end=END):
    path = Path(model_path)
    if not path.is_file():
        raise ValueError("frozen model artifact is missing")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("expected model SHA-256 required")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ValueError("frozen model artifact hash mismatch")
    if (start, end) != (START, END):
        raise ValueError("this replay is restricted to the registered consumed 2026 interval")
    return actual


def summarize_report(report):
    required = {"return", "cost", "bench", "account", "value", "total_cost", "total_turnover"}
    if not required <= set(report.columns) or len(report) < 2:
        raise ValueError("complete Qlib report required")
    net = (1 + report["return"] - report["cost"]).prod() - 1
    benchmark = (1 + report["bench"]).prod() - 1
    observations = len(report) - 1
    account = report["account"]
    values = {
        "sessions": len(report),
        "start": report.index.min().strftime("%Y-%m-%d"),
        "end": report.index.max().strftime("%Y-%m-%d"),
        "net_compound_return_pct": float(net * 100),
        "net_annualized_pct": float(((1 + net) ** (242 / observations) - 1) * 100),
        "benchmark_compound_return_pct": float(benchmark * 100),
        "compound_excess_pct": float((net - benchmark) * 100),
        "max_drawdown_pct": float((account / account.cummax() - 1).min() * 100),
        "average_exposure_pct": float((report["value"].iloc[1:] / account.iloc[1:]).mean() * 100),
        "cost_pct_initial": float(report["total_cost"].iloc[-1] / account.iloc[0] * 100),
        "turnover_x_initial": float(report["total_turnover"].iloc[-1] / account.iloc[0]),
        "final_account": float(account.iloc[-1]),
    }
    if any(not math.isfinite(value) for value in values.values() if isinstance(value, float)):
        raise ValueError("finite replay metrics required")
    return values


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pred-output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--expected-model-sha256", default=EXPECTED_MODEL_SHA256)
    args = parser.parse_args(argv)
    model_sha = verify_frozen_inputs(args.model, args.expected_model_sha256)

    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.evaluate import backtest_daily
    from qlib.data.dataset import DatasetH

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    with Path(args.model).open("rb") as stream:
        model = pickle.load(stream)
    handler = Alpha158(
        start_time="2016-01-04",
        end_time=END,
        fit_start_time="2016-01-04",
        fit_end_time="2021-12-31",
        instruments="csi500",
    )
    dataset = DatasetH(handler=handler, segments={"test": (START, END)})
    prediction = model.predict(dataset, segment="test")
    if isinstance(prediction, pd.Series):
        prediction = prediction.to_frame("score")
    dates = prediction.index.get_level_values("datetime")
    if dates.min().strftime("%Y-%m-%d") != START or dates.max().strftime("%Y-%m-%d") != END:
        raise ValueError("prediction interval does not match the registered replay")
    pred_path = Path(args.pred_output)
    pred_path.parent.mkdir(parents=True, exist_ok=True)
    prediction.to_pickle(pred_path)

    strategy = {
        "class": "TopkDropoutStrategy",
        "module_path": "qlib.contrib.strategy",
        "kwargs": {"signal": prediction, "topk": 100, "n_drop": 2, "risk_degree": 0.95},
    }
    report, _ = backtest_daily(
        start_time=START,
        end_time=END,
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
    report_path = Path(args.report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_pickle(report_path)
    summary = summarize_report(report)
    summary.update({
        "status": "FIXED_REPLAY_ON_CONSUMED_2026",
        "method_changed_after_open": False,
        "model_sha256": model_sha,
        "prediction_sha256": hashlib.sha256(pred_path.read_bytes()).hexdigest(),
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "target_net_return_pct": 20.0,
        "target_status": "PASS" if summary["net_compound_return_pct"] >= 20 else "FAIL",
    })
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
