# Operating-profitability source module verified on original reports

The separate Chinese operating-profitability source module and immutable
generator are implemented and exercised on both original SH600166 filings.
All24 reviewed monetary cells match, two current-year measures independently
recompute, and all50 consumed inputs remain unchanged. No stock ranking,
strategy return,2026 financial/market value or investment admission was added.
The frozen three-period investment objective remains active and unachieved.

## Frozen original execution

Method/source request was pushed as
`2f528856c3058d777db20f3dc94a2a149a430549`; local and remote heads were explicitly
matched before execution. Request SHA256:
`f10d41236e80caf401ec538f70cb9803538f196e2d65d0e416339677cdf87a1d`.
The actual source-only run emitted7 files in a new local directory. The public
[summary](../../experiments/qlib/operating-profitability-source-results.json)
and [independent check](../../experiments/qlib/operating-profitability-source-independent-check.json)
are byte-identical copies. Independent-check SHA256:
`3a460448155a305bfdfc2aab688b45c517059e7e21a885191b3d6e4e0d76f9ad`.

The originals are unchanged:

- Fiscal2023, published2024-04-27, announcement1219874919, PDF SHA256
  `e7588a7d935897aed750034c6847b0f57ab923c4837484f18e3bf62387b67eef`.
- Fiscal2024, published2025-04-26, announcement1223327299, PDF SHA256
  `bce69ed22306f3a0cc5b6a62eef9f2fab05d8a3c148f9715fd86faf937540410`.

The numerator is consolidated revenue minus COGS, selling expenses and admin
expenses; separately reported R&D stays separate. The denominator is prior
December31 assets in the same filing. These are accounting-source measures,
**not stock or portfolio returns**:

| Current fiscal year | Operating numerator, CNY | Same-edition lagged assets, CNY | Source ratio, rounded here |
|---|---:|---:|---:|
|2023|2,709,086,959.90|48,518,057,775.80|0.055836673686|
|2024|2,707,160,708.07|44,885,094,665.28|0.060313133530|

The independent calculation uses the manually reviewed raw-cell literals and
stdlib Decimal, without importing the production source parser or calculator.
It checks both exact60-digit ratios, the output identities and50 frozen inputs.
This is a separate arithmetic/identity check, not a fresh independent visual
review of all source pages or an investment-effectiveness evaluation.

Both current and comparative raw columns remain in each filing record. The
comparative income column has no same-filing two-year-lagged asset denominator,
so no comparative ratio is invented. Original2023 COGS and the later restated
comparative remain separate. No denominator or expense is borrowed across PDFs.

All8 historical OBSERVED queries are empty because the saved actual arrival is
in2026. Eight explicitly conditional publication-day-end queries preserve the
old snapshot when the future filing is present. The module emits all visible
supported source editions; it cannot decide latest eligible investment data.

## Tests and independent code review

The initial12 source-contract tests and5 generator tests each failed before
implementation and then passed. One independent code reviewer identified two
Important issues: normalization could contradict the original unit/currency
quote; final-summary persistence could escape the failure lifecycle. Root
reproduced four failing regressions and fixed both before source freeze, with
no additional review seat or silent source rerun. Legitimate scoped CNY and
pinned CAS inference remain supported. Partial summary output is staged;
completion requires successful postcheck/persistence and atomic publication.

After actual execution, a real-row regression fixture adds12 unchanged original
physical-page texts from the two reports, with original PDF/page hashes and
the independent expected values. CI does not fetch/authenticate the PDFs: it
proves parser/visibility regression behavior on those versioned excerpts.
All24 targeted tests pass; the full local suite passes1336 tests. The source
freeze's three CI jobs passed in
[run39903350248](https://github.com/shouldnotappearcalm/stock-rsi-lab/actions/runs/39903350248).
The final publication commit requires its own exact-head CI verification.

## Remaining research gates

This is an explicit Chinese source definition, not exact Compustat/CSMAR or
full cash-profitability replication. It supplies one issuer's engineering
evidence. The next step is a separately frozen coverage audit of the existing
394-issuer/1236-report pre2026 corpus, reusing authenticated page caches and
retaining every unsupported and newer filing. Do not zero-fill missing expenses
or backfill from a supported older report. Source-format support does not prove
financial-sector/economic comparability or representative investable coverage.

Only after coverage and numeric QA can a separately frozen candidate be tested
on2024/2025, followed by the already-exposed2026 interval. Historical observed
arrival, execution liquidity, real-world taxes, complete October returns and
future profitability remain unproved. No account, previous rejected strategy,
fractional-allocation failure or outcome was modified by this source module.
