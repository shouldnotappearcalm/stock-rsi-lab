"""One source-pinned MASTER training and development-only CSI500 replay.

The official MASTER network is imported from a separately cloned, pinned
source checkout. Market and stock panels must match their recorded hashes.
No 2026 query or portfolio search is permitted here.
"""
import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.prepare_qlib_master_stock_pre2026 import SEGMENTS
from scripts.run_qlib_tra_pre2026 import summarize


SOURCE_COMMIT = "de8f58557096abde4216a701b35fc4368158d111"
MARKET_SHA256 = "b1b9c3fa8d634aa33ed24b610d3d1edee882dbc0981c9f3c296f1aca50bebccc"
STOCK_SHA256 = "e9fe81ac31184a9aa1726dd22c0c102be6bda21fd34dfba5ab192c3e6e62aaf0"
FAST_SHA256 = "98e3eb14736a41cc9369251b7c1e86532bc010d32a61ec22c76c0b710c9a108e"
EPOCHS_MAX = 10
STEPS_PER_EPOCH = 480
TRAIN_LOSS_STOP = 0.95
TEST_START = SEGMENTS["development"][0]
TEST_END = SEGMENTS["development"][1]


class DailySequences:
    """Eight past observed sessions per stock, with same-date market features."""

    def __init__(self, panel, market):
        import numpy as np
        import pandas as pd

        if list(panel.index.names) != ["instrument", "datetime"]:
            raise ValueError("stock panel index must be instrument/datetime")
        if list(market.index.names) != ["datetime"] or market.shape[1] != 63:
            raise ValueError("market panel must have 63 fields by datetime")
        if panel["feature"].shape[1] != 158 or panel.index.has_duplicates:
            raise ValueError("stock panel must have 158 unique feature rows")
        dates = panel.index.get_level_values("datetime")
        instruments = panel.index.get_level_values("instrument")
        if dates.max() >= pd.Timestamp("2026-01-01") or market.index.max() >= pd.Timestamp("2026-01-01"):
            raise ValueError("post-2025 input is forbidden")
        if not panel.index.is_monotonic_increasing:
            raise ValueError("stock panel must be ordered by instrument and date")
        self.index = panel.index
        self.labels = panel["label"].iloc[:, 0].to_numpy(dtype="float32")
        self.stock = panel["feature"].to_numpy(dtype="float32")
        self.market = market.to_numpy(dtype="float32")
        self.dates = market.index
        self.date_codes = self.dates.get_indexer(dates)
        if (self.date_codes < 0).any():
            raise ValueError("stock dates absent from market calendar")
        n = len(panel)
        changes = np.r_[True, instruments[1:] != instruments[:-1]]
        self.group_start = np.maximum.accumulate(np.where(changes, np.arange(n), 0))
        self.rows_by_date = np.argsort(self.date_codes, kind="stable")
        sorted_codes = self.date_codes[self.rows_by_date]
        self.date_bounds = np.searchsorted(sorted_codes, np.arange(len(self.dates) + 1))

    def batch(self, date):
        import numpy as np

        date_id = self.dates.get_loc(date)
        rows = self.rows_by_date[self.date_bounds[date_id]:self.date_bounds[date_id + 1]]
        lookback = np.arange(7, -1, -1)
        history = rows[:, None] - lookback[None, :]
        valid = history >= self.group_start[rows, None]
        history = np.maximum(history, self.group_start[rows, None])
        if (self.date_codes[history] > date_id).any():
            raise ValueError("future feature entered MASTER sequence")
        stock = self.stock[history].copy()
        market = self.market[self.date_codes[history]].copy()
        stock[~valid] = 0.0
        market[~valid] = 0.0
        features = np.concatenate((stock, market), axis=2)
        return rows, features, self.labels[rows]

    def dates_between(self, start, end):
        return list(self.dates[(self.dates >= start) & (self.dates <= end)])


def train_label_subset(features, labels):
    import numpy as np

    keep = np.isfinite(labels)
    features, labels = features[keep], labels[keep]
    if len(labels) < 100:
        raise ValueError("fewer than 100 matured daily stock labels")
    tail = int(0.025 * len(labels))
    if tail > 0:
        order = np.argsort(labels)
        keep = np.zeros(len(labels), dtype=bool)
        keep[order[tail:-tail]] = True
        features, labels = features[keep], labels[keep]
    scale = labels.std(ddof=1)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("degenerate cross-sectional training label")
    return features, (labels - labels.mean()) / scale


def import_official_master(root):
    source = Path(root)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if commit != SOURCE_COMMIT:
        raise ValueError("official MASTER source commit mismatch")
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=source, text=True
    ).strip()
    if dirty:
        raise ValueError("official MASTER source checkout is modified")
    sys.path.insert(0, str(source))
    return importlib.import_module("master").MASTER


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--master-source-root", required=True)
    parser.add_argument("--market-pred", required=True)
    parser.add_argument("--stock-panel", required=True)
    parser.add_argument("--fast-pred", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("output directory already exists")
    if STOCK_SHA256.startswith("TO_BE_"):
        raise ValueError("stock panel hash must be frozen before training")
    for path, expected in ((args.market_pred, MARKET_SHA256), (args.stock_panel, STOCK_SHA256),
                           (args.fast_pred, FAST_SHA256)):
        if sha256_file(path) != expected:
            raise ValueError(f"input hash mismatch: {path}")

    import numpy as np
    import pandas as pd
    import qlib
    import torch
    from qlib.constant import REG_CN
    from qlib.contrib.evaluate import backtest_daily

    MASTER = import_official_master(args.master_source_root)
    panel = pd.read_pickle(args.stock_panel)
    market = pd.read_pickle(args.market_pred)
    sequences = DailySequences(panel, market)
    del panel, market
    torch.set_num_threads(4)
    torch.manual_seed(0)
    np.random.seed(0)
    model = MASTER(158, 256, 4, 2, 0.5, 0.5, 158, 221, 2)
    optimizer = torch.optim.Adam(model.parameters(), lr=8e-6)
    train_dates = sequences.dates_between(*SEGMENTS["train"][:2])
    if not train_dates or train_dates[-1].strftime("%Y-%m-%d") != SEGMENTS["train"][1]:
        raise ValueError("incomplete MASTER training dates")
    output.mkdir(parents=True)
    history = []
    rng = np.random.default_rng(0)
    for epoch in range(EPOCHS_MAX):
        model.train()
        losses = []
        for date in rng.permutation(train_dates)[:STEPS_PER_EPOCH]:
            _, features, labels = sequences.batch(date)
            if len(labels) < 100:
                continue
            features, labels = train_label_subset(features, labels)
            x = torch.from_numpy(features)
            y = torch.from_numpy(labels)
            pred = model(x)
            loss = torch.mean((pred - y) ** 2)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_value_(model.parameters(), 3.0)
            optimizer.step()
            losses.append(float(loss.detach()))
        train_loss = float(np.mean(losses))
        if len(losses) != STEPS_PER_EPOCH or not np.isfinite(train_loss):
            raise ValueError("incomplete or nonfinite MASTER training epoch")
        history.append({"epoch": epoch + 1, "train_loss": train_loss, "steps": len(losses)})
        print(json.dumps(history[-1]), flush=True)
        if train_loss <= TRAIN_LOSS_STOP:
            break
    model_path = output / "model.pt"
    torch.save(model.state_dict(), model_path)

    model.eval()
    prediction = []
    for date in sequences.dates_between(TEST_START, TEST_END):
        rows, features, _ = sequences.batch(date)
        with torch.no_grad():
            scores = model(torch.from_numpy(features)).detach().numpy()
        prediction.append(pd.Series(scores, index=sequences.index[rows]))
    scores = pd.concat(prediction).swaplevel().sort_index()
    if not np.isfinite(scores.to_numpy()).all():
        raise ValueError("nonfinite MASTER prediction")
    if scores.index.get_level_values("datetime").min() != pd.Timestamp(TEST_START) or scores.index.get_level_values("datetime").max() != pd.Timestamp(TEST_END):
        raise ValueError("incomplete or post-2025 MASTER predictions")
    scores = scores.to_frame("score")
    prediction_path = output / "pred.pkl"
    scores.to_pickle(prediction_path)
    fast = pd.read_pickle(args.fast_pred).loc[TEST_START:TEST_END]

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=20)
    results = {}
    for name, signal in (("master", scores), ("fast_control", fast)):
        report, _ = backtest_daily(
            start_time=TEST_START, end_time=TEST_END,
            strategy={"class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy",
                      "kwargs": {"signal": signal, "topk": 100, "n_drop": 2, "risk_degree": 0.95}},
            benchmark="SH000905", account=100_000_000,
            exchange_kwargs={"limit_threshold": 0.095, "deal_price": "close",
                             "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5},
        )
        report_path = output / f"{name}_report.pkl"
        report.to_pickle(report_path)
        results[name] = summarize(report) | {"report_sha256": sha256_file(report_path)}
    result = {
        "status": "PRE2026_DEVELOPMENT_ONLY", "candidate_budget": 1,
        "source_commit": SOURCE_COMMIT, "seed": 0,
        "architecture": "official MASTER d_model256 t_heads4 s_heads2 beta2 dropout0.5",
        "training": {"epochs_max": EPOCHS_MAX, "steps_per_epoch": STEPS_PER_EPOCH,
                      "train_loss_stop": TRAIN_LOSS_STOP,
                      "lr": 8e-6, "history": history},
        "start": TEST_START, "end": TEST_END,
        "portfolio": {"topk": 100, "n_drop": 2, "risk_degree": 0.95},
        "market_features_sha256": MARKET_SHA256, "stock_panel_sha256": STOCK_SHA256,
        "fast_prediction_sha256": FAST_SHA256,
        "model_sha256": sha256_file(model_path),
        "prediction_sha256": sha256_file(prediction_path),
        "results": results,
        "2026_market_data_accessed": False,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
