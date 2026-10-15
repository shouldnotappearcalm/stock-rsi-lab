"""Build MASTER's 63 index-market features without opening 2026 data.

This is a data-readiness artifact, not a trained model or investment result.
The formulas follow the official MASTER market-information definition, with
Qlib RobustZScoreNorm's training-only median/MAD and [-3, 3] clipping.
"""
import argparse
import hashlib
import json
from pathlib import Path


START = "2016-01-04"
FIT_END = "2021-12-29"
END = "2025-12-30"
INDEXES = ("SH000300", "SH000905", "SH000906")
WINDOWS = (5, 10, 20, 30, 60)


def index_fields():
    ret = "$close/Ref($close,1)-1"
    fields = [ret]
    for window in WINDOWS:
        fields.extend((
            f"Mean({ret},{window})", f"Std({ret},{window})",
            f"Mean($amount,{window})/$amount", f"Std($amount,{window})/$amount",
        ))
    return tuple(fields)


def normalize_training_only(raw, fit_end=FIT_END):
    import numpy as np
    import pandas as pd

    if list(raw.index.names) != ["datetime"] or raw.index.has_duplicates:
        raise ValueError("market features require unique datetime index")
    if raw.index.max() >= pd.Timestamp("2026-01-01"):
        raise ValueError("post-2025 market features are forbidden")
    if raw.shape[1] != 63 or raw.isna().any().any() or not np.isfinite(raw.to_numpy()).all():
        raise ValueError("market features must be 63 complete finite columns")
    train = raw.loc[:fit_end]
    if train.empty or train.index.min() != pd.Timestamp(START):
        raise ValueError("missing training feature dates")
    center = np.nanmedian(train.to_numpy(), axis=0)
    scale = (np.nanmedian(np.abs(train.to_numpy() - center), axis=0) + 1e-12) * 1.4826
    normalized = pd.DataFrame(
        np.clip((raw.to_numpy() - center) / scale, -3, 3).astype("float32"),
        index=raw.index, columns=raw.columns,
    )
    return normalized, {"center": center.tolist(), "scale": scale.tolist()}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


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
    from qlib.data import D

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    fields = index_fields()
    frame = D.features(list(INDEXES), list(fields), start_time=START, end_time=END)
    if list(frame.index.names) != ["instrument", "datetime"]:
        raise ValueError("unexpected Qlib index order")
    dates_by_index = {}
    blocks = []
    for instrument in INDEXES:
        part = frame.loc[instrument]
        if part.index.min() != pd.Timestamp(START) or part.index.max() != pd.Timestamp(END):
            raise ValueError(f"incomplete market date range for {instrument}")
        if part.index.has_duplicates or not np.isfinite(part.to_numpy()).all():
            raise ValueError(f"incomplete or nonfinite index features for {instrument}")
        dates_by_index[instrument] = part.index
        part = part.copy()
        part.columns = [f"{instrument}:{i:02d}" for i in range(len(fields))]
        blocks.append(part)
    if not all(dates_by_index[INDEXES[0]].equals(dates_by_index[i]) for i in INDEXES[1:]):
        raise ValueError("three indexes do not share the same daily calendar")
    raw = pd.concat(blocks, axis=1)
    raw.index.name = "datetime"
    normalized, fit = normalize_training_only(raw)

    output.mkdir(parents=True)
    raw_path = output / "raw.pkl"
    normalized_path = output / "normalized.pkl"
    raw.to_pickle(raw_path)
    normalized.to_pickle(normalized_path)
    result = {
        "status": "PRE2026_DATA_READINESS_ONLY",
        "source_method": "MASTER official 63 market information fields",
        "indexes": list(INDEXES), "field_expressions_per_index": list(fields),
        "start": START, "fit_end": FIT_END, "end": END,
        "sessions": int(len(raw)), "columns": int(raw.shape[1]),
        "train_sessions": int(len(raw.loc[:FIT_END])),
        "raw_missing_cells": int(raw.isna().sum().sum()),
        "normalized_missing_cells": int(normalized.isna().sum().sum()),
        "raw_sha256": sha256_file(raw_path),
        "normalized_sha256": sha256_file(normalized_path),
        "normalization": "training-only median/MAD*1.4826, clipped [-3,3]",
        "normalization_fit": fit,
        "2026_market_data_accessed": False,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key not in ("normalization_fit", "field_expressions_per_index")}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
