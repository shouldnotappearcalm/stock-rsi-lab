"""Persist feature-only Alpha158 inputs and a frozen training normalizer.

No forward-return expression is loaded: the temporary label is identically
zero. This allows December 30 signals for the complete 2025 account replay
without fetching any 2026 labels.
"""
import argparse
import json
from pathlib import Path

from scripts.prepare_qlib_master_market_pre2026 import sha256_file


START = "2016-01-04"
END = "2025-12-30"
FIT_END = "2021-12-29"
NO_FORWARD_LABEL = "$close/$close-1"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")

    import numpy as np
    import qlib
    from qlib.constant import REG_CN
    from qlib.contrib.data.handler import Alpha158
    from qlib.data.dataset.handler import DataHandlerLP

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    handler = Alpha158(
        start_time=START, end_time=END, fit_start_time=START, fit_end_time=FIT_END,
        instruments="csi500", label=[NO_FORWARD_LABEL], learn_processors=[],
        infer_processors=[
            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
        ],
    )
    features = handler.fetch(slice(START, END), col_set="feature", data_key=DataHandlerLP.DK_I)
    if list(features.index.names) != ["datetime", "instrument"]:
        features = features.reorder_levels(["datetime", "instrument"]).sort_index()
    if features.shape[1] != 158 or features.index.has_duplicates:
        raise ValueError("unique Alpha158 feature rows required")
    if not np.isfinite(features.to_numpy()).all():
        raise ValueError("nonfinite normalized stock features")
    features = features.astype("float32")
    normalizer = handler.infer_processors[0]
    state = {
        "kind": "Qlib RobustZScoreNorm", "fit_start": START, "fit_end": FIT_END,
        "columns": list(features.columns), "center": normalizer.mean_train.tolist(),
        "scale": normalizer.std_train.tolist(), "clip": [-3, 3], "fillna": 0,
    }
    output.mkdir(parents=True)
    feature_path = output / "features.pkl"
    normalizer_path = output / "normalizer.json"
    features.to_pickle(feature_path)
    normalizer_path.write_text(json.dumps(state, indent=2) + "\n")
    result = {
        "status": "PRE2026_FEATURES_ONLY", "start": START, "end": END,
        "normalization_fit_end": FIT_END, "temporary_label": NO_FORWARD_LABEL,
        "feature_columns": 158, "rows": len(features),
        "sessions": int(features.index.get_level_values("datetime").nunique()),
        "feature_sha256": sha256_file(feature_path),
        "normalizer_sha256": sha256_file(normalizer_path),
        "forward_return_labels_loaded": False, "2026_market_values_queried": False,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
