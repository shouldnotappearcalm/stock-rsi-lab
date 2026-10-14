# Qlib Alpha158 pre-2026 development run

## Decision

The first evidence-backed high-exposure candidate is Qlib Alpha158 with DoubleEnsemble signals on
CSI500 and a bounded TopkDropout portfolio. The method came from the Qlib official benchmark rather
than facts observed in the consumed 2026 interval.

All configured dates end by 2025-12-30:

| Role | Dates |
| --- | --- |
| Model training | 2016-01-04—2021-12-31 |
| Early-stop validation | 2022-01-04—2023-12-29 |
| Development inference/backtest | 2024-01-02—2025-12-30 |

The Qlib dataset contains later bytes, but DatasetH, predictions and backtest configuration did not
request 2026. The candidate is therefore eligible for further development, not for a retrospective
claim about 2026.

## Results

The official `topk=50, n_drop=5` DoubleEnsemble configuration produced 24.63% net compound
annualized return, 98.73% average exposure and -23.00% account drawdown. Its turnover was excessive:
107.09 times initial capital over two years, costing 10.66% of initial capital.

A predeclared 15-candidate portfolio search kept the signal fixed and varied only `topk/n_drop`.
The selection rule maximized the worse of the 2024 and 2025 returns, then used annualized return net
of a cost penalty as tie-break. It retained `topk=100, n_drop=2`:

| Metric | Retained development result |
| --- | ---: |
| Two-year net compound return | **61.47%** |
| Net compound annualized return | **27.13%** |
| 2024 net return | 11.47% |
| 2025 net return | 44.85% |
| Average exposure | **99.58%** |
| Maximum drawdown | -20.12% |
| Cost / initial capital | 2.23% |
| Turnover / initial capital | 22.84x |

The registered 20% annualized development target is met. The stronger condition “20% in every
calendar year” is not met. A strong 2025 still drives much of the result.

## Interpretation

This is a better starting policy than hand-written single-factor rules because it uses a fixed,
published 158-feature catalog, cross-sectional normalization, an independently fitted ranking model
and a high-exposure portfolio with bounded replacement. It still has material limitations:

- the Qlib price-limit threshold is a simplified 9.5% rule;
- the accepted historical ST/suspension and exact daily-limit layers are not joined yet;
- execution uses daily close and Qlib's simulator rather than the project's next-open broker;
- development outcomes selected portfolio parameters, so 2024-2025 cannot validate further edits;
- no prospective or sealed test has been opened.

## External evidence reviewed

- [Qlib benchmark table](https://github.com/microsoft/qlib/blob/main/examples/benchmarks/README.md)
- [Official LightGBM Alpha158 workflow](https://github.com/microsoft/qlib/blob/main/examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml)
- [Qlib enhanced indexing example](https://github.com/microsoft/qlib/tree/main/examples/portfolio)
- [Listwise learn-to-rank A-share paper](https://arxiv.org/abs/2104.12484)

The listwise paper reports 38% annual return for a long-short construction. That number is not used
as evidence for this long-only A-share candidate; only the ranking objective remains a future module
candidate.

Machine-readable results, artifact hashes and all 15 portfolio candidates are in
[`pre2026-development-results.json`](../../experiments/qlib/pre2026-development-results.json).
