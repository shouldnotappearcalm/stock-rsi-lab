# Fixed DoubleEnsemble + TRA signal blend

The previous DoubleEnsemble signal had strong 2025 returns but a weaker 2024, while the independently trained [TRA first-pass signal](qlib-tra-first-pass-pre2026-2026-10-16.md) was more balanced. Before reading any blend outcome, commit `4251808` fixed exactly one candidate: daily percentile ranks of both signals on the shared 500 CSI500 names, averaged 50/50, then Top100/Drop2 with 95% risk degree and the same Qlib exchange costs. A DoubleEnsemble-only control was replayed on exactly the same 482 sessions, 2024-01-02 through 2025-12-26. The script verifies both prediction hashes and refuses 2026 dates.

| Metric | Fast DE control | Fixed DE + TRA blend | TRA first pass |
| --- | ---: | ---: | ---: |
| 2024 net return | 11.47% | 9.03% | **18.13%** |
| 2025 net return | **45.11%** | 23.45% | 19.69% |
| Net annualized | **27.37%** | 16.12% | 19.03% |
| Two-year compound | **61.75%** | 34.59% | 41.38% |
| Compound excess over CSI500 | **+24.37 pp** | -2.79 pp | +4.00 pp |
| Maximum drawdown | -20.12% | -18.56% | **-15.51%** |
| Average exposure | 99.58% | 99.81% | 99.83% |

The blend lost 11.25 annualized percentage points versus DE and reduced 2024 return as well. The hypothesized complementarity did not appear in this fixed portfolio test. It failed both the annualized and per-year 20% development targets. No blend weight was changed after inspection, and nothing was run on the already consumed 2026 interval.

The full [machine result](../../experiments/qlib/de-tra-blend-pre2026-results.json) includes artifact hashes and both report hashes. This is an increasingly reused 2024–2025 development interval, so even a later candidate crossing a threshold here would remain a research lead, not a sealed performance claim. Qlib close execution and simplified price limits also remain.
