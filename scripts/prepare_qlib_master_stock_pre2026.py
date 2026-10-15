"""Persist a causal Alpha158/CSI500 panel for one bounded MASTER probe.

The five-session target is used only for training and later development
evaluation. Every registered signal's target matures before 2026 starts.
"""
import argparse
import json
from pathlib import Path

from scripts.prepare_qlib_master_market_pre2026 import START, FIT_END, sha256_file


END = "2025-12-23"
LABEL = "Ref($close,-5)/Ref($close,-1)-1"
SEGMENTS = {
    "train": (START, "2021-12-23", "2021-12-30"),
    "valid": ("2022-01-04", "2023-12-22", "2023-12-29"),
    "development": ("2024-01-02", END, "2025-12-30"),
}


def assert_registered_windows(calendar):
    for name, (start, end, maturity) in SEGMENTS.items():
        days = calendar(start, maturity)
        days = [str(day)[:10] for day in days]
        if end not in days or len(days) <= days.index(end) + 5 or days[days.index(end) + 5] != maturity:
            raise ValueError(f"{name} five-session label maturity mismatch")
    if END >= "2026-01-01":
        raise ValueError("post-2025 signal is forbidden")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")

    import numpy as np
    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.data.handler import Alpha158
    from qlib.data import D
    from qlib.data.dataset.handler import DataHandlerLP

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    assert_registered_windows(lambda start, end: D.calendar(start_time=start, end_time=end))
    handler = Alpha158(
        start_time=START, end_time=END,
        fit_start_time=START, fit_end_time=FIT_END,
        instruments="csi500",
        infer_processors=[
            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
        ],
        learn_processors=[], label=[LABEL],
    )
    panel = handler.fetch(slice(START, END), col_set=["feature", "label"], data_key=DataHandlerLP.DK_I)
    if list(panel.index.names) != ["instrument", "datetime"]:
        raise ValueError("unexpected stock panel index")
    if panel["feature"].shape[1] != 158 or panel["label"].shape[1] != 1:
        raise ValueError("MASTER stock panel requires 158 features and one label")
    if panel.index.has_duplicates or panel.index.get_level_values("datetime").max() > pd.Timestamp(END):
        raise ValueError("stock panel has duplicate or post-2025 signal dates")
    if not np.isfinite(panel["feature"].to_numpy()).all():
        raise ValueError("nonfinite stock features")
    panel = panel.astype("float32")
    date_index = panel.index.get_level_values("datetime")
    metrics = {}
    for name, (start, end, maturity) in SEGMENTS.items():
        subset = panel[(date_index >= pd.Timestamp(start)) & (date_index <= pd.Timestamp(end))]
        if subset.empty or subset.index.get_level_values("datetime").min() != pd.Timestamp(start):
            raise ValueError(f"missing {name} stock dates")
        metrics[name] = {
            "start": start, "end": end, "last_label_maturity": maturity,
            "rows": int(len(subset)),
            "sessions": int(subset.index.get_level_values("datetime").nunique()),
            "labeled_rows": int(subset["label"].notna().sum().sum()),
        }
    output.mkdir(parents=True)
    panel_path = output / "panel.pkl"
    panel.to_pickle(panel_path)
    result = {
        "status": "PRE2026_DATA_READINESS_ONLY",
        "source_method": "MASTER stock Alpha158 CSI500 with five-session target",
        "start": START, "end": END, "normalization_fit_end": FIT_END,
        "label": LABEL, "rows": int(len(panel)),
        "feature_columns": 158, "label_columns": 1,
        "feature_nonfinite_cells": 0,
        "segments": metrics,
        "panel_sha256": sha256_file(panel_path),
        "2026_market_data_accessed": False,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
