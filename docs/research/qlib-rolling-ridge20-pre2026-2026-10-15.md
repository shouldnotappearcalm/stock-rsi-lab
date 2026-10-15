# Qlib rolling Ridge with a 20-session target

Qlib's [dynamic benchmark](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/examples/benchmarks_dynamic/README.md) includes RR[Linear]: a Ridge model refitted as the data distribution moves. This bounded A-share probe kept the earlier 20-session label, 24 purged prediction windows, Top100/Drop5 portfolio, costs and development dates unchanged. It substituted Qlib's Ridge model (`alpha=0.05`) for LightGBM and included the recent validation segment in each fit, since a fixed Ridge fit has no early stopping.

The script was frozen at `fda8fa7` before the run. Each prediction block used only labels that had matured before its first signal date. The final test label matured by 2025-12-29; no 2026 market fact was accessed.

| Metric | Rolling Ridge | Rolling LightGBM |
| --- | ---: | ---: |
| Net compound return | **36.61%** | 24.66% |
| Net annualized return | **17.79%** | 12.27% |
| 2024 net return | **12.13%** | 1.06% |
| 2025 through Nov 28 | 21.83% | **23.36%** |
| Compound excess over CSI500 | **+7.10 pp** | -4.85 pp |
| Average exposure | 99.45% | 99.58% |
| Maximum drawdown | **-17.10%** | -21.65% |
| Turnover / initial capital | 49.49x | **47.32x** |
| Cost / initial capital | 4.90% | **4.69%** |

Ridge improved both total return and 2024 substantially, supporting a simpler, regularized signal over repeated boosted trees in this particular rolling protocol. It still failed the 20% annualized development target, and its roughly 49x turnover over the period is expensive. It is retained as a component input for the *already frozen* equal-rank multi-horizon blend, not promoted as an investment strategy. Full metrics, 24 dated windows and hashes are in [`rolling-ridge20-pre2026-results.json`](../../experiments/qlib/rolling-ridge20-pre2026-results.json).
