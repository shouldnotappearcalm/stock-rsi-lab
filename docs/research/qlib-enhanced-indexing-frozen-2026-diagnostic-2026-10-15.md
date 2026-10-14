# Frozen enhanced-indexing 2026 diagnostic

## Result

The pre-2026 enhanced-indexing candidate was frozen before this run. Its signal, optimizer and wake
rule remained unchanged: frozen DoubleEnsemble predictions, `lamb=1.0`, `delta=0.2`, `b_dev=0.02`,
99% risk degree and first-session-of-week rebalancing. The diagnostic harness was committed as
`a584217` before the result was observed.

| Metric | EnhancedIndexing | Frozen Top100 / Drop2 | CSI500 |
| --- | ---: | ---: | ---: |
| 2026-01-05—2026-10-13 net return | **-3.79%** | -2.00% | -5.10% |
| Excess over CSI500 | +1.30% | **+3.10%** | — |
| Annualized net return | -4.96% | -2.62% | — |
| Average exposure | 94.92% | **99.42%** | — |
| Maximum drawdown | **-15.54%** | -16.30% | — |
| Cost / initial capital | **0.72%** | 0.78% | — |
| Turnover / initial capital | **7.74x** | 8.31x | — |
| Final account from CNY 100m | CNY 96.21m | CNY 98.00m | — |

The 20% absolute-return target failed. The enhanced portfolio lost 1.80 percentage points more than
the frozen Top100/Drop2 portfolio and produced 1.80 percentage points less excess return. It reduced
drawdown, turnover and cost, but those improvements did not compensate for weaker stock allocation.
Average exposure also missed the 95% development threshold by 0.08 percentage points, while staying
above 90%.

All 39 weekly optimizations returned `optimal`; no constraint was relaxed. A second identical run
matched percentage metrics within `2.3e-13` and report numeric values within `1.1e-7`.

## Interpretation boundary

This is a diagnostic on a previously consumed interval. It is not sealed evidence and cannot be used
to select another method. The result is recorded as a failed transfer from 2024—2025 development to
2026 absolute returns. No parameter, factor, risk model or wake rule will be changed from facts in
this run.

Machine-readable metrics, artifact hashes, data receipts and comparison deltas are in
[`enhanced-indexing-frozen-2026-diagnostic-results.json`](../../experiments/qlib/enhanced-indexing-frozen-2026-diagnostic-results.json).
