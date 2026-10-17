"""Fixed three-arm daily-target rolling campaign, selected before 2026 opens.

Arms: rolling Ridge, fixed-budget rolling LightGBM, and a 50/50 daily rank
blend of frozen DE and rolling Ridge. An unchanged DE control participates
in the same predeclared worst-calendar-year selection rule.
"""
import argparse
import json
import math
import pickle
from datetime import date
from pathlib import Path

from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_cninfo_orj_signal_pre2026 import price_input_digest
from scripts.run_qlib_rolling20_pre2026 import summarize
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.rolling_daily import MatureDailyLabels, rolling_windows


START = "2024-01-02"
LAST_SIGNAL = "2025-12-30"
ACCOUNT_END = "2025-12-31"
FEATURE_SHA256 = "5a47abbc3be7ce8bde51ced20fb52d04c51e4b2b97af84653300afb4fc42277f"
PRICE_SHA256 = "f2095c539f181aa0297dda84434e7e0fce8a87d4133c97f3fc2e7e327abc4eb8"
DE_SHA256 = "98e3eb14736a41cc9369251b7c1e86532bc010d32a61ec22c76c0b710c9a108e"
LGB_PARAMS = {
    "objective": "regression", "learning_rate": 0.05, "colsample_bytree": 0.8879,
    "subsample": 0.8789, "lambda_l1": 205.6999, "lambda_l2": 580.9768,
    "max_depth": 8, "num_leaves": 210, "num_threads": 4,
    "seed": 0, "deterministic": True, "force_col_wise": True, "verbosity": -1,
}


def rank_development(results):
    required = ("2024_return_pct", "2025_return_pct", "average_exposure_pct",
                "net_annualized_pct", "cost_pct_initial")
    if not results or any(not math.isfinite(row[key]) for row in results.values() for key in required):
        raise ValueError("finite complete development metrics required")
    eligible = [name for name, metrics in results.items()
                if metrics["2024_return_pct"] > 0 and metrics["2025_return_pct"] > 0
                and metrics["average_exposure_pct"] >= 90]
    return sorted(eligible, key=lambda name: (
        min(results[name]["2024_return_pct"], results[name]["2025_return_pct"]),
        results[name]["net_annualized_pct"], -results[name]["cost_pct_initial"], name,
    ), reverse=True)


def equal_rank_blend(first, second):
    import pandas as pd

    ranked = []
    for frame in (first, second):
        values = frame.iloc[:, 0] if isinstance(frame, pd.DataFrame) else frame
        ranked.append(values.groupby(level="datetime").rank(pct=True))
    joined = pd.concat(ranked, axis=1, join="inner").dropna()
    if joined.empty or joined.groupby(level="datetime").size().min() < 400:
        raise ValueError("rolling blend has insufficient shared prediction coverage")
    return joined.mean(axis=1).to_frame("score")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--de-prediction", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")
    if FEATURE_SHA256.startswith("TO_BE_") or PRICE_SHA256.startswith("TO_BE_"):
        raise ValueError("rolling campaign inputs must be frozen before training")
    if sha256_file(args.features) != FEATURE_SHA256 or sha256_file(args.de_prediction) != DE_SHA256:
        raise ValueError("rolling campaign data identity changed")

    import lightgbm as lgb
    import numpy as np
    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.evaluate import backtest_daily
    from sklearn.linear_model import Ridge
    from threadpoolctl import threadpool_limits

    features = pd.read_pickle(args.features)
    if list(features.index.names) != ["datetime", "instrument"] or features.index.has_duplicates:
        raise ValueError("unique chronological feature rows required")
    if features.index.get_level_values("datetime").max() >= pd.Timestamp("2026-01-01"):
        raise ValueError("2026 features cannot enter development")
    symbols = sorted(features.index.get_level_values("instrument").unique())
    if price_input_digest(args.provider_uri, symbols) != PRICE_SHA256:
        raise ValueError("rolling campaign raw label prices changed")
    snapshot = QlibSnapshot(args.provider_uri)
    calendar = tuple(day for day in snapshot.calendar if date(2016, 1, 4) <= day <= date(2025, 12, 31))
    receipts = list(rolling_windows(calendar, START, LAST_SIGNAL))
    labels = MatureDailyLabels(snapshot, calendar)
    output.mkdir(parents=True)
    (output / "models").mkdir()
    predictions = {"rolling_ridge": [], "rolling_lgb": []}
    fits = []
    for number, receipt in enumerate(receipts, 1):
        print(json.dumps({"rolling_fit": number, "total": len(receipts), **receipt}), flush=True)
        training = features.loc[receipt["train_start"]:receipt["train_end"]]
        target = labels.targets(training.index, receipt["fit_asof"])
        keep = target.notna().to_numpy()
        x = training.to_numpy(dtype="float64")[keep]
        y = target.to_numpy(dtype="float64")[keep]
        test = features.loc[receipt["prediction_start"]:receipt["prediction_end"]]
        if not np.isfinite(x).all() or len(x) < 100_000 or test.empty:
            raise ValueError("incomplete or nonfinite rolling fit input")
        ridge = Ridge(alpha=0.05, solver="cholesky")
        with threadpool_limits(limits=4):
            ridge.fit(x, y)
        ridge_path = output / "models" / f"ridge_{number:02d}.pkl"
        with ridge_path.open("wb") as stream:
            pickle.dump(ridge, stream)
        predictions["rolling_ridge"].append(pd.Series(ridge.predict(test.to_numpy()), index=test.index))
        tree = lgb.train(LGB_PARAMS, lgb.Dataset(x, label=y), num_boost_round=100)
        tree_path = output / "models" / f"lgb_{number:02d}.txt"
        tree.save_model(str(tree_path))
        predictions["rolling_lgb"].append(pd.Series(tree.predict(test.to_numpy()), index=test.index))
        fits.append(receipt | {"training_rows": len(x), "latest_label_price_read": labels.latest_read.isoformat(),
                               "ridge_sha256": sha256_file(ridge_path), "lgb_sha256": sha256_file(tree_path)})
        if labels.latest_read.isoformat() > receipt["fit_asof"]:
            raise ValueError("rolling target reader crossed fit time")
        (output / "fit_receipts.json").write_text(json.dumps(fits, indent=2) + "\n")
    signals = {}
    for name, parts in predictions.items():
        signal = pd.concat(parts).sort_index().to_frame("score")
        if signal.index.has_duplicates or not np.isfinite(signal.to_numpy()).all():
            raise ValueError("invalid rolling predictions")
        expected_days = pd.DatetimeIndex([day for day in calendar if START <= day.isoformat() <= LAST_SIGNAL])
        if not signal.index.get_level_values("datetime").unique().equals(expected_days):
            raise ValueError("rolling prediction calendar is incomplete")
        if signal.groupby(level="datetime").size().min() < 400:
            raise ValueError("rolling prediction universe is incomplete")
        signals[name] = signal
    control = pd.read_pickle(args.de_prediction).loc[START:LAST_SIGNAL]
    signals["de_ridge_equal_rank"] = equal_rank_blend(control, signals["rolling_ridge"])
    signals = {"de_control": control, **signals}
    prediction_hashes = {}
    for name, signal in signals.items():
        path = output / (name + "_pred.pkl")
        signal.to_pickle(path)
        prediction_hashes[name] = sha256_file(path)
    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    results = {}
    for name, signal in signals.items():
        print("portfolio replay " + name, flush=True)
        report, _ = backtest_daily(
            start_time=START, end_time=ACCOUNT_END,
            strategy={"class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy",
                      "kwargs": {"signal": signal, "topk": 100, "n_drop": 2, "risk_degree": 0.95}},
            benchmark="SH000905", account=100_000_000,
            exchange_kwargs={"limit_threshold": 0.095, "deal_price": "close",
                             "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5},
        )
        path = output / (name + "_report.pkl")
        expected_days = pd.DatetimeIndex([day for day in calendar if START <= day.isoformat() <= ACCOUNT_END])
        if not report.index.equals(expected_days):
            raise ValueError("full-year account replay calendar is incomplete")
        report.to_pickle(path)
        results[name] = summarize(report) | {"report_sha256": sha256_file(path)}
        if name == "de_control":
            legacy = summarize(report.loc[:"2025-12-30"])
            if abs(legacy["net_annualized_pct"] - 27.134313367415185) > 1e-5:
                raise ValueError("rolling study control does not reproduce prior DE baseline")
    ranked = rank_development(results)
    selected = ranked[0] if ranked else None
    result = {
        "status": "PRE2026_DEVELOPMENT_ONLY", "candidate_budget": 3,
        "start": START, "last_signal": LAST_SIGNAL, "account_end": ACCOUNT_END,
        "label": "close(t+2)/close(t+1)-1, daily cross-sectional rank normalized",
        "rolling": {"history_sessions": 1210, "step_sessions": 20, "label_maturity_sessions": 2,
                    "anchor": START, "reset_at_year_boundary": False},
        "models": {"ridge_alpha": 0.05, "lgb_params": LGB_PARAMS, "lgb_trees": 100,
                   "blend": "fixed 50/50 daily percentile rank DE + rolling Ridge"},
        "portfolio": {"topk": 100, "n_drop": 2, "risk_degree": 0.95},
        "selection": "positive full 2024/2025, >=90% exposure, then maximize worst calendar year, annualized return, negative cost",
        "ranked_eligible": ranked, "selected": selected,
        "development_status": ("NEW_LEAD_ONLY" if selected and selected != "de_control" else "NO_NEW_LEAD"),
        "results": results, "prediction_sha256": prediction_hashes,
        "features_sha256": FEATURE_SHA256, "raw_price_inputs_sha256": PRICE_SHA256,
        "fit_receipts_sha256": sha256_file(output / "fit_receipts.json"),
        "fit_count": len(fits), "2026_market_values_queried": False,
        "2026_target_status": "NOT_EVALUATED", "claim_status": "DEVELOPMENT_ONLY_NOT_SEALED",
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
