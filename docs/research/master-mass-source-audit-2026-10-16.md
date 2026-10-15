# Two independent A-share methods after the fixed blend failed

The fixed DE+TRA development blend failed at 16.12% net annualized. Further weight variants on the same repeatedly inspected 2024–2025 interval would be adaptive search. We cloned two independent, paper-linked implementations to identify genuinely different modules and their data requirements. Neither supplied a result for our 2024–2025 protocol, and neither was run against the already exposed 2026 interval.

## MASTER: market-conditioned cross-stock signal

Official [paper](https://ojs.aaai.org/index.php/AAAI/article/view/27767) and [source](https://github.com/SJTU-DMTai/MASTER) at clone commit `de8f58557096abde4216a701b35fc4368158d111`. The architecture in `master.py` gates 158 stock features with market information, then applies temporal and cross-stock attention. It is structurally different from DoubleEnsemble, rolling linear forecasts and TRA's temporal state router.

The source cannot be treated as a ready 2024–2025 replay:

- The included 63-column market-information CSV ends on 2022-12-30. It needs a newly reconstructed, date-aligned 2024–2025 market feature stream from the three index histories.
- The published Qlib workflow targets 2020-07 through 2022-12, uses CSI800 and a five-session label. Its data and portfolio are not the current CSI500/Top100 protocol.
- The authors explicitly [document](https://github.com/SJTU-DMTai/MASTER#about-validation) an error in their released validation data processing. They say their original checkpoints/results are unaffected under their training-loss stopping rule, but those checkpoints cannot be substituted for a locally trained model with a known preprocessing fit and data lineage.

A data-readiness probe now reconstructs all 63 raw fields from the three index histories, using only current and trailing price/amount formulas. It covers 2,429 common trading days from 2016-01-04 through 2025-12-30 with zero missing cells. The median/MAD normalization uses only 1,459 training days through 2021-12-29, clips at ±3, and has a separate output hash. The [script](../../scripts/prepare_qlib_master_market_pre2026.py) and [manifest](../../experiments/qlib/master-market-pre2026-manifest.json) allow that part to be repeated without the original CSV or 2026 data.

This resolves the market-index feature availability question. It does not resolve the stock-level Alpha158 sequence construction, label maturity, fresh training cost or portfolio replay. A valid investment probe must build and verify those components before freezing one checkpoint and testing. Published IC or old checkpoints are not evidence of our net portfolio return.

## MASS: heterogeneous investor signals and disagreement

Official [paper](https://arxiv.org/abs/2505.10278) and [source](https://github.com/gta0804/MASS) at clone commit `68edcaae9e6ac099d28eed90513219495b0852b7`. `basic_agent.py` has eight modality flags spanning valuation, dividend, growth, quality, news, base data, industry, risk and price. `investment_analyzer.py` aggregates investor-type scores by a weighted mean penalized for disagreement; `agent_distribution.py` searches type weights with simulated annealing on historical rank IC. These suggest independent factor views and an explicit aggregation module for a future harness.

The released code is not an executable net-return reproduction on our data. The [README](https://github.com/gta0804/MASS#what-you-need-to-know) says the full dataset will be released later and estimates 80 GiB RAM for the default SSE50 configuration. The current `main.py` asks for pool and label parquet files absent from the clone; the trainer additionally reads Wind-news files absent there. Its `InvestmentAnalyzer.record_score` and aggregation methods create a fresh `threading.Lock()` on each call rather than using a shared lock, so concurrent writes require repair before reuse. Its published signal IC is not our after-cost portfolio result.

The reusable idea is the **contract**, not the reported performance: independently timestamped modality scores, a fixed disagreement-aware aggregator, and an optimizer whose label maturity is checked at every wake. Reproducing MASS would require licensed/news/PIT fundamental data, resource and concurrency repair, an equal-budget deterministic aggregation control, and a wholly separate future test.

These audits do not identify a credible strategy with more than 20% net return in 2026. The 2026-01-05—2026-10-13 interval was already exposed and cannot be rehabilitated by testing another candidate on it.
