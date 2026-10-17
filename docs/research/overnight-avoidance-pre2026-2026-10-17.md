# Fixed weak-overnight-trend avoidance module

The independent source is [Guo et al. (2025)](https://doi.org/10.1016/j.jedc.2024.104997), available before 2026. Its risk-adjusted evidence is concentrated in the weak-stock short leg; the strong-stock long leg does not establish a standalone long-only alpha. The local hypothesis therefore used the weak trend as an avoidance module on frozen DoubleEnsemble rankings, not as a top-decile stock picker.

Commit `e08cbfc` fixed one candidate before outcomes: adjusted overnight gross returns compound over eleven complete months under the 12–2 convention; skip the most recent month; each execution month demote the lowest decile of scorable names below the normal DE ranking. Formation coverage must exceed 80% per month and 80% per universe. Missing factors express no opinion. Top100/Drop2, 95% risk degree and Qlib costs stay fixed; existing weak holdings unwind under the same turnover limit. This is an adaptation to CSI500 and lacks the paper's historical market-cap exclusion.

All 24 monthly formation receipts passed their time checks. Minimum universe coverage was 97.8%; each monthly weak list had 48–49 names. The first cutoff was 2023-11-30 and the last 2025-10-31. The same-date DE control reproduced its existing 2024/2025 metrics within the registered tolerance.

| Net metric | DE control | Weak-trend avoidance |
| --- | ---: | ---: |
| 2024 return | **11.47%** | 6.96% |
| 2025 through Dec 30 | **44.85%** | 44.33% |
| Annualized development return | **27.13%** | 24.30% |
| Maximum drawdown | **-20.12%** | -21.88% |
| Average exposure | 99.58% | 99.60% |

The module reduced the worse-year return and annualized return, failing the frozen development improvement gate. No exclusion-percentage or lookback search followed, and 2026 was not evaluated. The [machine result](../../experiments/qlib/ovnt-avoidance-pre2026-results.json) records input, signal, report and monthly-formation hashes.

The user's current target is separately [registered](../../experiments/a-share-10pct-2026-objective.json): positive full-year 2024 and 2025 net returns and at least 10% net in January–October 2026. This diagnostic ends on 2025-12-30, so it does not itself verify full-year 2025 coverage. Existing 2026 data stop on October 13; complete October results do not yet exist in the local evidence. The target remains unmet.
