# Qlib TRA chronological first-pass development probe

The next independent signal candidate was [Qlib TRA](https://github.com/microsoft/qlib/tree/54355232463878d2eebb91fe0ee5fa7fa1f5976c/examples/benchmarks/TRA), a temporal routing model with three latent states. Its 20 Alpha158 features, one-session trade target, train/validation/test dates, 10-epoch-per-phase budget and Top100/Drop2 portfolio were frozen in `b8ef28b`, before the result was read. Training covered 2016–2021; validation covered 2022–2023; this development replay covers 2024-01-02 through 2025-12-26. The latest development label matures inside 2025.

The Qlib implementation calls `test_epoch` from `fit`, writes its first test scores to `model/test_pred.pkl`, and updates shared loss memory as it walks daily batches. A second `predict(test)` on that same dataset would reuse test-period error memory from the full first pass. The replay therefore extracts only the saved first-pass `score` column. This causal repair and independent replay path were frozen at `8b7ffc9` and `e874ee5` before the portfolio outcome was opened. Qlib's daily evaluation iterator is chronological, and its state sequence excludes the inferred label horizon. The saved file and extracted score have separate hashes in the machine record.

| Metric | TRA first pass |
| --- | ---: |
| 2024 net return | +18.13% |
| 2025 net return | +19.69% |
| Two-year net compound | +41.38% |
| Net annualized | +19.03% |
| CSI500 compound | +37.38% |
| Compound excess | +4.00 pp |
| Maximum drawdown | -15.51% |
| Average exposure | 99.83% |
| Cost / initial capital | 2.33% |
| Turnover / initial capital | 23.80x |

This missed the 20% annualized target and both yearly 20% targets. It is a development observation, not a promoted strategy. The close-price execution convention, simplified 9.5% limit and repeatedly inspected 2024–2025 interval still restrict the inference. The already exposed 2026 interval was not read or used to choose this method.

The full [machine result](../../experiments/qlib/tra-first-pass-pre2026-results.json) records the model, prediction, first-pass raw file and report hashes. The 2024/2025 complementarity with the previously frozen DoubleEnsemble motivated one fixed, equal-rank 50/50 blend, frozen separately at `4251808` before it ran. No weight search follows that check.
