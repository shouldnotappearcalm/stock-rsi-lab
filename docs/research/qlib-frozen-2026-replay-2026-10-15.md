# Frozen Qlib method replay on 2026

## Method identity

The method was fixed from pre-2026 development before this replay:

- model: Qlib Alpha158 DoubleEnsemble;
- model fit: 2016-01-04—2021-12-31;
- early-stop validation: 2022-01-04—2023-12-29;
- portfolio selection: 2024-01-02—2025-12-30 only;
- universe: CSI500;
- portfolio: Top-100, replace at most 2 names per session, 95% risk degree;
- execution proxy: daily close, 5 bps open cost, 15 bps close cost, 5 yuan minimum;
- frozen model SHA-256: `0ac63a71bc6777257ce18cef62340c2666065397d059a319af39653b93ba280f`;
- frozen config SHA-256: `3d5cdc287326e0b4b6e5a3b34571bc4b2de552e6645aa2455c91a5d5fb149732`.

No retraining, parameter selection or method change occurred after the 2026 replay began.

## Result

| Metric | 2026-01-05—2026-10-13 |
| --- | ---: |
| Sessions | 185 |
| Net compound return | **-2.00%** |
| Annualized return | -2.62% |
| CSI500 compound return | -5.10% |
| Compound excess return | +3.10% |
| Average exposure | **99.42%** |
| Maximum drawdown | -16.30% |
| Cost / initial capital | 0.78% |
| Turnover / initial capital | 8.31x |
| Final value from 100 million | 98.00 million |
| Registered +20% target | **FAIL** |

The policy preserved high exposure and beat CSI500, but lost money and missed the absolute-return
target by about 22 percentage points.

## Evidence status

This interval had already been observed during earlier, invalid exploratory work. The replay is
therefore recorded as `FIXED_REPLAY_ON_CONSUMED_2026`, not as sealed or untouched evidence. It is
useful for answering how the independently frozen Qlib method behaves, but cannot restore the
interval's unseen status.

The result must not be used to modify the method and then claim validation on the same interval.
Further evolution requires a new experiment identity and a new prospective sealed window.

## Remaining execution limitations

- Qlib uses a simplified 9.5% price-limit threshold rather than the accepted point-in-time legal
  limit table.
- Historical ST/suspension evidence is not joined to this Qlib simulation.
- Execution uses daily close rather than the project's next-open lot/T+1 broker.
- The result is a fixed model replay, not deployable trading evidence.

Machine-readable metrics are in
[`frozen-method-2026-replay-results.json`](../../experiments/qlib/frozen-method-2026-replay-results.json).
