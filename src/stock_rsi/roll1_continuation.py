"""Continue a frozen rolling cadence; never reset it at a year boundary."""
from datetime import date

from stock_rsi.rolling_daily import rolling_windows


def continuation_windows(calendar, previous, history=1210, step=20):
    calendar = tuple(calendar)
    if not previous:
        raise ValueError("previous frozen fit receipts required")
    extended = list(rolling_windows(calendar, previous[0]["prediction_start"],
                                    calendar[-1].isoformat(), history=history, step=step,
                                    permitted_end=calendar[-1].isoformat()))
    if len(extended) < len(previous):
        raise ValueError("continuation cannot shorten the prior cadence")
    keys = ("train_start", "train_end", "fit_asof", "latest_label_maturity", "prediction_start")
    for old, new in zip(previous, extended):
        if any(old[key] != new[key] for key in keys) or old["prediction_end"] > new["prediction_end"]:
            raise ValueError("previous fit cadence does not match the extended calendar")
    last_old = date.fromisoformat(previous[-1]["prediction_end"])
    first_new = calendar[calendar.index(last_old) + 1].isoformat()
    result = []
    for number, window in enumerate(extended, 1):
        if window["prediction_end"] <= last_old.isoformat():
            continue
        result.append(window | {"scheduled_prediction_start": window["prediction_start"],
                                "prediction_start": max(window["prediction_start"], first_new),
                                "number": number, "reuse_existing": number <= len(previous)})
    return result


def normalize_frozen_features(raw, state):
    import numpy as np

    if (state["fit_end"] != "2021-12-29" or list(raw.columns) != state["columns"]
            or state["clip"] != [-3, 3] or state["fillna"] != 0):
        raise ValueError("frozen normalizer identity or feature columns changed")
    center = np.asarray(state["center"], dtype="float32")
    scale = np.asarray(state["scale"], dtype="float32")
    if (center.shape != (len(raw.columns),) or scale.shape != center.shape
            or not np.isfinite(center).all() or not np.isfinite(scale).all() or (scale <= 0).any()):
        raise ValueError("finite positive frozen normalizer scale required")
    result = raw.astype("float32").copy()
    result -= center
    result /= scale
    result = result.clip(-3, 3).fillna(0)
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError("nonfinite frozen-normalized features")
    return result.astype("float32")
