# RSI finance search round 2: factor loops and portfolio-aware objectives

## Scope and non-interference

This round started after the consumed 2026 diagnostic, but did not use any local 2026 market
observation or prior diagnostic metric. All executable comparison dates end in 2025. Sources were
searched independently and cloned
to `/private/tmp`; decisions below come from papers, fixed source commits and 2024—2025 development
runs.

## Sources inspected

| Source | Fixed version | What is real | Decision |
| --- | --- | --- | --- |
| [FactorMiner](https://github.com/minihellboy/factorminer) | `e0d6adf` | Formula DSL, marginal admission, delay challenges, trial ledger, Qlib CN walk-forward study | Reuse its evaluator ideas; do not assume factor mining raises portfolio return |
| [QuantaAlpha](https://github.com/QuantaAlpha/QuantaAlpha) | `b7ceb27` | Trajectory lineage, mutation/crossover, separate test backtest | Do not copy RankIC as the primary evolution reward |
| [MOSAIC-Agents](https://github.com/haphap/MOSAIC-Agents) | `558f07a` | Git prompt mutations, cooldown, backtest identities, A-share plumbing | Do not use as investment core: PRISM training is a stub and JANUS is mainly a live same-date construct |
| [AQuA](https://arxiv.org/abs/2608.12841) | arXiv v3 | Separate factor/model loops, fixed sandboxes, constrained expression/config diffs | Adopt separation and access control; no public implementation was located |
| [AlphaSeek](https://arxiv.org/abs/2608.13913) | arXiv v1 | Trajectory-level evolution and redundancy-aware factor portfolio | Method reference only; reported CSI300 ARR is 8.28% and no matching public code was located |

FactorMiner supplies the strongest negative evidence. Its Qlib China benchmark covers 30 campaigns,
35,711 evaluated formulas and 471 LightGBM fits. Marginal admission adds about 0.0032 RankIC over a
tuned Alpha158 baseline, but none of the mined arms significantly changes the top-50 spread. Its own
conclusion is that the admission objective must match what the portfolio trades.

QuantaAlpha retains complete trajectories, but
[`StrategyTrajectory.get_primary_metric`](https://github.com/QuantaAlpha/QuantaAlpha/blob/b7ceb27b1001261d7a95b209a963664ae1f8ab23/quantaalpha/pipeline/evolution/trajectory.py#L90)
returns RankIC and later selection sorts on that value. This repeats the objective mismatch observed
by FactorMiner. MOSAIC has useful operational constraints, but its
[`train_cohort`](https://github.com/haphap/MOSAIC-Agents/blob/558f07a99a28aea437718c0227f856fa556821ca/mosaic/prism/trainer.py#L14)
explicitly returns that full training still requires future integration; it is not evidence for a
working regime-trained investment ensemble.

## Executed experiment

The first bounded experiment used FactorMiner's portfolio-aware LightGBM implementation at the fixed
commit above. It compared exactly three objectives on CSI500 Alpha158:

- train: 2015-01-01—2021-12-31;
- validation: 2022-01-01—2023-12-31;
- development test: 2024-01-01—2025-12-31;
- objectives: ordinary MSE, top-sextile-weighted MSE, and daily LambdaRank;
- fixed comparison: Top50/Drop5 with Qlib costs;
- portfolio follow-up: the same pre-existing 15 TopK/Dropout candidates for MSE and top-weighted MSE;
- seed 0 was the admission probe; a losing objective received no additional seed budget.

At fixed Top50/Drop5, top-weighted MSE improved after-cost annualized excess from -3.02% to +0.48%
and lowered mean daily turnover from 19.78% to 16.91%. LambdaRank failed directly, with negative
RankIC and -9.07% after-cost annualized excess.

The same portfolio search reversed the apparent top-weighted improvement:

| Objective | Selected portfolio | Net annualized | 2024 | 2025 | Max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| MSE | Top200/Drop5 | **19.78%** | **6.38%** | 34.75% | **-19.75%** |
| Top-weighted MSE | Top100/Drop1 | 16.77% | -1.02% | **37.66%** | -25.81% |
| LambdaRank | rejected before search | — | — | — | — |

All three objective candidates failed the 20% annualized target. Top-weighted MSE optimized a local
Top50 measure but did not improve the selected portfolio's worse calendar year. No objective was
retained and no extra seeds were run.

## Project decision

Do not add formula count, memory, prompt roles or RankIC-based evolution yet. The next model candidate
must change the signal's treatment of non-stationarity while retaining portfolio-aware admission.
Qlib TRA is the next bounded candidate because its router explicitly models multiple temporal
patterns and has an official Alpha158 implementation. It requires a separate PyTorch runtime and a
predeclared training budget; it must still beat the frozen MSE control on 2024 and 2025 before any
future evaluation.

Machine-readable objective metrics, all 30 searched portfolios and artifact hashes are in
[`topbook-objectives-pre2026-results.json`](../../experiments/qlib/topbook-objectives-pre2026-results.json).
