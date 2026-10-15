# Fixed equal-rank multi-horizon signal blend

One-session DoubleEnsemble and 20-session rolling Ridge target different price movements. A fixed 50/50 blend of their **daily cross-sectional percentile ranks** was committed at `089bb96` before the Ridge development outcome was opened. The comparison used the same CSI500 sessions (2024-01-02—2025-11-28), Top100/Drop5 portfolio, 95% risk degree and Qlib costs for the blend and fast-only control. All 500 daily names had both signals.

| Metric | Equal-rank blend | Fast only |
| --- | ---: | ---: |
| Net compound return | 27.85% | **41.51%** |
| Net annualized return | 13.76% | **19.99%** |
| 2024 net return | **8.81%** | 6.00% |
| 2025 through Nov 28 | 17.50% | **33.50%** |
| Compound excess over CSI500 | -1.66 pp | **+12.00 pp** |
| Average exposure | 99.57% | 99.40% |
| Maximum drawdown | **-17.78%** | -22.01% |
| Turnover / initial capital | 49.53x | **45.32x** |
| Cost / initial capital | 4.91% | **4.49%** |

The blend softened the 2024 drawdown and return weakness but materially harmed 2025 and overall after-cost returns. It failed both the 20% annualized threshold and the required incremental lift over the fast control. No weight search follows. Full metrics and prediction/report hashes are in [`multihorizon-blend-pre2026-results.json`](../../experiments/qlib/multihorizon-blend-pre2026-results.json). This is development evidence only; the consumed 2026 interval was not used.
