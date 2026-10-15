"""One bounded, pre-2026 Qlib TRA signal experiment on CSI500.

This is a separate signal-model candidate. The portfolio and exchange settings
are the already registered Top100/Drop2 control; no portfolio search runs here.
"""
import argparse
import hashlib
import json
from pathlib import Path


START = "2016-01-04"
TRAIN_END = "2021-12-29"  # two-session target remains inside 2021
VALID_START = "2022-01-04"
VALID_END = "2023-12-27"  # two-session target remains inside 2023
TEST_START = "2024-01-02"
TEST_END = "2025-12-26"  # two-session target remains inside 2025
FEATURES = (
    "RESI5", "WVMA5", "RSQR5", "KLEN", "RSQR10", "CORR5", "CORD5", "CORR10",
    "ROC60", "RESI10", "VSTD5", "RSQR60", "CORR60", "WVMA60", "STD5",
    "RSQR20", "CORD60", "CORD10", "CORR20", "KLOW",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_window(train_end=TRAIN_END, valid_end=VALID_END, test_end=TEST_END):
    if not (START < train_end < VALID_START < valid_end < TEST_START < test_end < "2026-01-01"):
        raise ValueError("TRA experiment must use disjoint pre-2026 windows")


def first_pass_score(saved_predictions):
    """Use the first chronological test pass saved by ``TRAModel.fit``.

    Calling ``predict(test)`` again would reuse test-label errors that the
    first pass wrote into the shared routing memory, including future dates.
    """
    import pandas as pd

    if not isinstance(saved_predictions, pd.DataFrame) or "score" not in saved_predictions:
        raise ValueError("TRA first-pass prediction must contain score")
    if list(saved_predictions.index.names) != ["datetime", "instrument"]:
        raise ValueError("TRA first-pass prediction index is invalid")
    dates = saved_predictions.index.get_level_values("datetime")
    if dates.min() < pd.Timestamp(TEST_START) or dates.max() > pd.Timestamp(TEST_END):
        raise ValueError("TRA first-pass prediction crossed the development interval")
    return saved_predictions[["score"]].dropna()


def summarize(report):
    net = (1 + report["return"] - report["cost"]).prod() - 1
    bench = (1 + report["bench"]).prod() - 1
    account = report["account"]
    result = {
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
    validate_window()

    import pandas as pd
    import qlib
    import torch
    from qlib.constant import REG_CN
    from qlib.contrib.data.dataset import MTSDatasetH
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.evaluate import backtest_daily
    from qlib.contrib.model.pytorch_tra import TRAModel

    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")
    output.mkdir(parents=True)
    torch.set_num_threads(4)
    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)

    handler = Alpha158(
        start_time=START, end_time=TEST_END,
        fit_start_time=START, fit_end_time=TRAIN_END,
        instruments="csi500",
        infer_processors=[
            {"class": "FilterCol", "kwargs": {"fields_group": "feature", "col_list": list(FEATURES)}},
            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
        ],
        learn_processors=[{"class": "CSRankNorm", "kwargs": {"fields_group": "label"}}],
        label=["Ref($close, -2) / Ref($close, -1) - 1"],
    )
    segments = {
        "train": (START, TRAIN_END),
        "valid": (VALID_START, VALID_END),
        "test": (TEST_START, TEST_END),
    }
    dataset = MTSDatasetH(
        handler=handler, segments=segments, seq_len=60, num_states=3,
        memory_mode="sample", batch_size=1024, drop_last=True,
    )
    model = TRAModel(
        model_type="RNN", seed=0, n_epochs=10, early_stop=4,
        max_steps_per_epoch=40, pretrain=True, eval_test=False,
        lr=1e-3, lamb=1.0, rho=0.99, alpha=0.5,
        transport_method="router", memory_mode="sample", logdir=str(output / "model"),
        model_config={
            "input_size": len(FEATURES), "hidden_size": 64, "num_layers": 2,
            "rnn_arch": "LSTM", "use_attn": True, "dropout": 0.0,
        },
        tra_config={
            "num_states": 3, "rnn_arch": "LSTM", "hidden_size": 32,
            "num_layers": 1, "dropout": 0.0, "tau": 1.0, "src_info": "LR_TPE",
        },
    )
    model.fit(dataset)
    predictions = first_pass_score(pd.read_pickle(output / "model/test_pred.pkl"))
    pred_path = output / "pred.pkl"
    predictions.to_pickle(pred_path)

    report, _ = backtest_daily(
        start_time=TEST_START, end_time=TEST_END,
        strategy={
            "class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy",
            "kwargs": {"signal": predictions, "topk": 100, "n_drop": 2, "risk_degree": 0.95},
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
        "model": "TRA Alpha158 selected20 RNN/LSTM router",
        "splits": segments,
        "seed": 0, "candidate_budget": 1,
        "training_budget": {"pretrain": True, "n_epochs_each_phase_max": 10,
                            "max_steps_per_epoch": 40, "early_stop": 4},
        "portfolio": {"topk": 100, "n_drop": 2, "risk_degree": 0.95},
        "metrics": summarize(report),
        "prediction_sha256": sha256_file(pred_path),
        "report_sha256": sha256_file(report_path),
        "model_sha256": sha256_file(output / "model/model.bin"),
        "2026_market_data_accessed": False,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
