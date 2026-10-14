"""Create trailing-window CSI500 structured covariance snapshots before 2026."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--price-start", default="2023-01-03")
    parser.add_argument("--risk-start", default="2023-12-29")
    parser.add_argument("--risk-end", default="2025-12-29")
    parser.add_argument("--lookback", type=int, default=240)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--allow-consumed-2026-diagnostic", action="store_true")
    args = parser.parse_args(argv)
    diagnostic = args.allow_consumed_2026_diagnostic and args.risk_end == "2026-10-12"
    if ((args.risk_end >= "2026-01-01" and not diagnostic)
            or args.price_start > args.risk_start or args.risk_start > args.risk_end):
        raise ValueError("risk snapshots must use a valid interval capped before 2026")
    if args.lookback < 60:
        raise ValueError("risk lookback is implausibly short")

    import numpy as np
    import pandas as pd
    import qlib
    from qlib.constant import REG_CN
    from qlib.data import D
    from qlib.model.riskmodel import StructuredCovEstimator

    qlib.init(provider_uri=args.provider_uri, region=REG_CN, kernels=1, logging_level=40)
    universe = D.features(
        D.instruments("csi500"), ["$close"], start_time=args.price_start, end_time=args.risk_end,
    ).swaplevel().sort_index()
    price = D.features(
        D.instruments("all"), ["$close"], start_time=args.price_start, end_time=args.risk_end,
    ).squeeze().unstack(level="instrument")
    model = StructuredCovEstimator()
    dates = price.index
    output = Path(args.output_dir)
    written = []
    for index in range(args.lookback - 1, len(price)):
        date = dates[index]
        if date < pd.Timestamp(args.risk_start) or date > pd.Timestamp(args.risk_end):
            continue
        codes = universe.loc[date].index
        window = price.iloc[index - args.lookback + 1:index + 1].reindex(columns=codes)
        returns = window.pct_change(fill_method="pad")
        returns = returns.clip(returns.quantile(0.025), returns.quantile(0.975), axis=1)
        exposure, covariance, residual_variance = model.predict(
            returns, is_price=False, return_decomposed_components=True,
        )
        root = output / date.strftime("%Y%m%d")
        root.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(exposure, index=codes).to_pickle(root / "factor_exp.pkl")
        pd.DataFrame(covariance).to_pickle(root / "factor_cov.pkl")
        pd.Series(np.sqrt(residual_variance), index=codes).to_pickle(root / "specific_risk.pkl")
        written.append(date.strftime("%Y-%m-%d"))
    if not written:
        raise ValueError("no risk snapshots generated")
    payload = {
        "price_start": args.price_start, "risk_start": written[0], "risk_end": written[-1],
        "lookback_sessions": args.lookback, "snapshot_count": len(written),
        "estimator": "qlib.model.riskmodel.StructuredCovEstimator",
        "classification": "CONSUMED_2026_DIAGNOSTIC" if diagnostic else "PRE2026_DEVELOPMENT",
    }
    manifest = Path(args.manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
