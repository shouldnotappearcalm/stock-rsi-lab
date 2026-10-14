# Qlib enhanced-indexing pre-2026 module evolution

## What changed

The DoubleEnsemble Alpha158 signal and its predictions stayed fixed. This mutation replaced the
`TopkDropout` portfolio constructor with a separate enhanced-indexing module:

- Qlib `StructuredCovEstimator` builds a 240-session trailing risk snapshot;
- CSI500 constituent weights and volume are read at the previous trading session;
- a long-only optimizer maximizes signal score relative to CSI500 while penalizing tracking risk;
- 99% of account equity is available to the portfolio;
- the first available trading session in each ISO week is the only portfolio wake.

Every prediction, risk snapshot, benchmark weight and backtest date ends before 2026. The consumed
2026 replay was neither read nor rerun.

## Fixed search budget

Six candidates changed one optimizer dimension around Qlib's documented defaults. Eligibility
required at least 20% net compound annualized return and at least 95% average exposure. Selection
maximized the worse of the 2024 and 2025 returns, then annualized return, shallower drawdown and
lower turnover. The search stopped after all six registered candidates.

The retained parameters are `lamb=1.0`, `delta=0.2`, `b_dev=0.02`.

| Metric | Retained result | Previous Top100 / Drop2 |
| --- | ---: | ---: |
| Two-year net compound return | **81.14%** | 61.47% |
| Net compound annualized return | **34.67%** | 27.13% |
| 2024 net return | **21.43%** | 11.47% |
| 2025 net return | **49.17%** | 44.85% |
| Average exposure | **97.74%** | 99.58% |
| Maximum drawdown | **-18.88%** | -20.12% |
| Cost / initial capital | 2.38% | **2.23%** |
| Turnover / initial capital | 24.23x | **22.84x** |

A clean second process reproduced all retained metrics within `1e-12` absolute tolerance. All 103
retained-candidate solves returned `optimal`; no constraint was removed and the largest checked
numerical violation was `7.27e-5` under the registered `1e-4` tolerance.

## Interpretation and gate status

The result passes the registered development gates and, unlike the prior portfolio, clears 20% in
both development calendar years. The gain came from portfolio construction rather than retraining or
changing the signal model. That is the modular RSI behavior this project needs: one module changed,
its inputs and wake schedule stayed explicit, and the comparison used the same prediction artifact.

This candidate is not cleared for a return claim or deployment. The project replaced Qlib's
constraint-relaxing ECOS fallback with an audited CLARABEL path: any infeasible solve fails that
candidate. The registered `delta=0.1` candidate became infeasible after 24 completed solves,
consumed its budget slot and was not replaced. The run still uses close execution, a simplified
9.5% limit rule and forward-filled monthly CSI500 weights. These remain visible limitations in
VerifyGate.

The already-observed 2026 interval cannot evaluate this mutation. The next valid outcome test must be
a newly registered future interval whose data remain unavailable until the method, dependencies and
hashes are frozen.

Machine-readable inputs, all six candidates and limitations are in
[`enhanced-indexing-pre2026-results.json`](../../experiments/qlib/enhanced-indexing-pre2026-results.json).
