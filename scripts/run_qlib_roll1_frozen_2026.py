"""One registered diagnostic of the pre-2026 winner, continuing the same account.

No candidate selection, parameter tuning or portfolio changes are allowed here.
The consumed 2026 period and incomplete October cannot establish sealed success.
"""
import argparse
import json
import math
import pickle
from datetime import date
from pathlib import Path

from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.replay_qlib_daily_evidence import replay_with_evidence
from scripts.run_cninfo_orj_signal_pre2026 import price_input_digest
from scripts.run_qlib_roll1_campaign_pre2026 import FEATURE_SHA256, LGB_PARAMS, PRICE_SHA256, rank_development
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.roll1_continuation import continuation_windows, normalize_frozen_features
from stock_rsi.rolling_daily import MatureDailyLabels


END = "2026-10-13"
NORMALIZER_SHA256 = "b3694091e592e8eba33baa2e90f3328ab7c0f3aee5b1508a8c191580171a1e0e"
METHOD_CODE_PATHS = (
    "scripts/run_qlib_roll1_campaign_pre2026.py", "scripts/run_qlib_roll1_frozen_2026.py",
    "scripts/replay_qlib_daily_evidence.py", "src/stock_rsi/rolling_daily.py",
    "src/stock_rsi/roll1_continuation.py", "src/stock_rsi/qlib_daily_evidence.py",
    "src/stock_rsi/qlib_snapshot.py",
)


def verify_development_selection(summary):
    if (summary.get("status") != "PRE2026_DEVELOPMENT_ONLY"
            or summary.get("account_end") != "2025-12-31"
            or summary.get("candidate_budget") != 3
            or summary.get("2026_market_values_queried") is not False):
        raise ValueError("completed pre-2026 selection required before opening diagnostic data")
    ranked = rank_development(summary["results"])
    selected = summary.get("selected")
    if (summary.get("development_status") != "NEW_LEAD_ONLY" or not ranked
            or selected != ranked[0] or summary.get("ranked_eligible") != ranked
            or selected not in {"rolling_ridge", "rolling_lgb", "de_ridge_equal_rank"}):
        raise ValueError("only the selected new development winner may enter this diagnostic")
    return selected


def calendar_year_metrics(report, year):
    import pandas as pd

    part = report.loc[year]
    before = report.loc[report.index < part.index[0]]
    if before.empty:
        raise ValueError("previous year-end account equity required")
    baseline = before.iloc[-1]
    initial = float(baseline["account"])
    net = float((1 + part["return"] - part["cost"]).prod() - 1)
    if not math.isclose(net, float(part["account"].iloc[-1]) / initial - 1, abs_tol=1e-9):
        raise ValueError("calendar net return and carried account equity disagree")
    nav = pd.concat([before["account"].iloc[-1:], part["account"]])
    bench = float((1 + part["bench"]).prod() - 1)
    result = {
        "sessions": len(part), "start": part.index[0].strftime("%Y-%m-%d"),
        "end": part.index[-1].strftime("%Y-%m-%d"), "starting_equity": initial,
        "final_equity": float(part["account"].iloc[-1]),
        "net_compound_return_pct": net * 100, "benchmark_compound_return_pct": bench * 100,
        "compound_excess_pct": (net - bench) * 100,
        "max_drawdown_pct": float((nav / nav.cummax() - 1).min() * 100),
        "average_exposure_pct": float((part["value"] / part["account"]).mean() * 100),
        "cost_pct_starting_equity": float((part["total_cost"].iloc[-1] - baseline["total_cost"]) / initial * 100),
        "turnover_x_starting_equity": float((part["total_turnover"].iloc[-1] - baseline["total_turnover"]) / initial),
    }
    if any(not math.isfinite(value) for value in result.values() if isinstance(value, float)):
        raise ValueError("finite calendar metrics required")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--development-dir", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--normalizer", required=True)
    parser.add_argument("--selection-receipt", required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--de-model")
    args = parser.parse_args(argv)
    output, development = Path(args.output_dir), Path(args.development_dir)
    if output.exists():
        raise ValueError("diagnostic output already exists; never overwrite a trial")
    if sha256_file(args.selection_receipt) != args.expected_selection_sha256:
        raise ValueError("frozen selection receipt changed")
    registration = json.loads(Path(args.selection_receipt).read_text())
    if (registration["status"] != "FROZEN_BEFORE_2026_REPLAY"
            or registration["maximum_2026_diagnostics"] != 1 or registration["end"] != END
            or registration["replay_script_sha256"] != sha256_file(__file__)
            or registration["development_summary_sha256"] != sha256_file(development / "summary.json")):
        raise ValueError("registered diagnostic identity changed")
    code_hashes = registration["method_code_sha256"]
    repo = Path(__file__).resolve().parents[1]
    if (set(code_hashes) != set(METHOD_CODE_PATHS)
            or any(sha256_file(repo / name) != code_hashes[name] for name in METHOD_CODE_PATHS)):
        raise ValueError("registered method source changed")
    summary = json.loads((development / "summary.json").read_text())
    selected = verify_development_selection(summary)
    if selected != registration["selected"]:
        raise ValueError("registered winner changed")
    if sha256_file(args.features) != FEATURE_SHA256 or sha256_file(args.normalizer) != NORMALIZER_SHA256:
        raise ValueError("frozen development feature/normalizer identity changed")
    if sha256_file(development / "fit_receipts.json") != summary["fit_receipts_sha256"]:
        raise ValueError("development training evidence changed")
    prior = json.loads((development / "fit_receipts.json").read_text())
    old_prediction = development / (selected + "_pred.pkl")
    if sha256_file(old_prediction) != summary["prediction_sha256"][selected]:
        raise ValueError("selected development predictions changed")
    kind = "lgb" if selected == "rolling_lgb" else "ridge"
    suffix = "txt" if kind == "lgb" else "pkl"
    for number, receipt in enumerate(prior, 1):
        if sha256_file(development / "models" / f"{kind}_{number:02d}.{suffix}") != receipt[kind + "_sha256"]:
            raise ValueError("frozen development model changed")
    if selected == "de_ridge_equal_rank":
        if not args.de_model or sha256_file(args.de_model) != registration["de_model_sha256"]:
            raise ValueError("frozen DE blend model required")

    import lightgbm as lgb
    import numpy as np
    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.data.handler import Alpha158
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP
    from sklearn.linear_model import Ridge
    from threadpoolctl import threadpool_limits

    historical_features = pd.read_pickle(args.features)
    historical_symbols = sorted(historical_features.index.get_level_values("instrument").unique())
    if price_input_digest(args.provider_uri, historical_symbols) != PRICE_SHA256:
        raise ValueError("frozen source price files changed")
    # The first 2026 market query occurs only after all selection checks above.
    output.mkdir(parents=True)
    (output / "models").mkdir()
    (output / "opened.json").write_text(json.dumps({"selection": registration, "parameter_changes_allowed": False}, indent=2) + "\n")
    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    handler = Alpha158(start_time="2025-12-31", end_time=END, instruments="csi500",
                       label=["$close/$close-1"], infer_processors=[], learn_processors=[])
    raw = handler.fetch(slice("2025-12-31", END), col_set="feature", data_key=DataHandlerLP.DK_I)
    if list(raw.index.names) != ["datetime", "instrument"]:
        raw = raw.reorder_levels(["datetime", "instrument"]).sort_index()
    extension = normalize_frozen_features(raw, json.loads(Path(args.normalizer).read_text()))
    extension.to_pickle(output / "features_extension.pkl")
    features = pd.concat([historical_features, extension]).sort_index()
    if features.index.has_duplicates or features.shape[1] != 158:
        raise ValueError("continuation features overlap or changed schema")
    snapshot = QlibSnapshot(args.provider_uri)
    calendar = tuple(day for day in snapshot.calendar if date(2016, 1, 4) <= day <= date.fromisoformat(END))
    windows = continuation_windows(calendar, prior)
    labels = MatureDailyLabels(snapshot, calendar)
    predictions, fits = [], []
    for window in windows:
        number = window["number"]
        print(json.dumps({"continuation_fit": number, "model": kind, **window}), flush=True)
        training_rows = None
        if window["reuse_existing"]:
            model_path = development / "models" / f"{kind}_{number:02d}.{suffix}"
            if kind == "ridge":
                with model_path.open("rb") as stream:
                    model = pickle.load(stream)
            else:
                model = lgb.Booster(model_file=str(model_path))
        else:
            training = features.loc[window["train_start"]:window["train_end"]]
            target = labels.targets(training.index, window["fit_asof"])
            keep = target.notna().to_numpy()
            x = training.to_numpy(dtype="float64")[keep]
            y = target.to_numpy(dtype="float64")[keep]
            if not np.isfinite(x).all() or len(x) < 100_000:
                raise ValueError("incomplete mature training data")
            training_rows = len(x)
            model_path = output / "models" / f"{kind}_{number:02d}.{suffix}"
            if kind == "ridge":
                model = Ridge(alpha=0.05, solver="cholesky")
                with threadpool_limits(limits=4):
                    model.fit(x, y)
                with model_path.open("wb") as stream:
                    pickle.dump(model, stream)
            else:
                model = lgb.train(LGB_PARAMS, lgb.Dataset(x, label=y), num_boost_round=100)
                model.save_model(str(model_path))
            if labels.latest_read.isoformat() > window["fit_asof"]:
                raise ValueError("continuation training crossed simulated fit time")
        test = features.loc[window["prediction_start"]:window["prediction_end"]]
        predictions.append(pd.Series(model.predict(test.to_numpy()), index=test.index))
        fits.append(window | {"training_rows": training_rows, "model_sha256": sha256_file(model_path),
                              "latest_label_price_read": labels.latest_read.isoformat() if labels.latest_read else None})
        (output / "fit_receipts.json").write_text(json.dumps(fits, indent=2) + "\n")
    continuation = pd.concat(predictions).sort_index().to_frame("score")
    if selected == "de_ridge_equal_rank":
        # Reconstruct the original DE feature processor, never fit on 2026.
        from scripts.run_qlib_roll1_campaign_pre2026 import equal_rank_blend
        de_handler = Alpha158(start_time="2016-01-04", end_time=END,
                              fit_start_time="2016-01-04", fit_end_time="2021-12-31",
                              instruments="csi500", label=["$close/$close-1"], learn_processors=[])
        dataset = DatasetH(handler=de_handler, segments={"test": ("2025-12-31", END)})
        with Path(args.de_model).open("rb") as stream:
            de = pickle.load(stream)
        de_prediction = de.predict(dataset, segment="test")
        continuation = equal_rank_blend(de_prediction, continuation)
    signal = pd.concat([pd.read_pickle(old_prediction), continuation]).sort_index()
    expected = pd.DatetimeIndex([day for day in calendar if "2024-01-02" <= day.isoformat() <= END])
    if (signal.index.has_duplicates or not np.isfinite(signal.to_numpy()).all()
            or not signal.index.get_level_values("datetime").unique().equals(expected)
            or signal.groupby(level="datetime").size().min() < 400):
        raise ValueError("continuation prediction coverage is incomplete")
    signal.to_pickle(output / "prediction.pkl")
    report, ledger = replay_with_evidence(signal, args.provider_uri, output / "account", "2024-01-02", END)
    old_report = development / (selected + "_report.pkl")
    if sha256_file(old_report) != summary["results"][selected]["report_sha256"]:
        raise ValueError("frozen development account report changed")
    pd.testing.assert_frame_equal(report.loc[:"2025-12-31"], pd.read_pickle(old_report),
                                  check_exact=False, atol=1e-5, rtol=1e-9)
    metrics = calendar_year_metrics(report, "2026")
    result = {
        "status": "FIXED_DIAGNOSTIC_ON_CONSUMED_2026", "selected": selected,
        "2024_return_pct": summary["results"][selected]["2024_return_pct"],
        "2025_return_pct": summary["results"][selected]["2025_return_pct"],
        "2026": metrics, "target_net_compound_return_pct": 10,
        "interim_threshold_met": metrics["net_compound_return_pct"] >= 10,
        "requested_full_October_complete": False, "objective_achieved": False,
        "selection_receipt_sha256": args.expected_selection_sha256,
        "features_extension_sha256": sha256_file(output / "features_extension.pkl"),
        "provider_price_inputs_sha256": price_input_digest(
            args.provider_uri, sorted(features.index.get_level_values("instrument").unique())),
        "provider_metadata_sha256": {name: sha256_file(Path(args.provider_uri) / name) for name in (
            "calendars/day.txt", "instruments/csi500.txt", "features/sh000905/close.day.bin")},
        "prediction_sha256": sha256_file(output / "prediction.pkl"),
        "fit_receipts_sha256": sha256_file(output / "fit_receipts.json"),
        "ledger": ledger, "rule_changed_after_2026_open": False,
        "2026_feedback_to_new_variants": False,
        "claim_status": "INCOMPLETE_OCTOBER_CONSUMED_DIAGNOSTIC_NOT_SEALED_NOT_FULL_PIT",
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
