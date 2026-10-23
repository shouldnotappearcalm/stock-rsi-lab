# 400 annual sources inspected; 2026 portfolio result remains pending

Subsequent stage: [all 68 monthly full-cohort visibility queries and their
separate reconstruction](asset-expansion-2026-availability-results-2026-10-23.md)
are complete. The extraction evidence below retains its original scope.

The unchanged total-assets parser completed all 400 original annual-report
candidates once. It produced 290 supported reports and 472 source cells,
including 182 reports with explicit same-edition current/prior December 31
columns. Another 24 cover identities and 86 financial-table schemas remained
unsupported. No source was dropped and no older report replaced a failed one.
The source cutoff remains October 21, 2026. No 2026 ranking or account return
was calculated in this stage; the full return objective remains open.

## Freeze and actual extraction

Request `28cd9c344dcba04a72dfbf19ecb46f73c0d64de05174b60b2700773edc8321ee`
was pushed in `f812d5fbcc6e67d6d398bb1ff010bf2b38210bcc` before source text
or financial extraction. That freeze passed 1,188 local tests and all three
[GitHub CI jobs](https://github.com/shouldnotappearcalm/stock-rsi-lab/actions/runs/39884537397).
The existing CI dependency repair declares Beautiful Soup and pypdf in
`requirements-test.txt`; checks and failure notifications remain enabled.

The foreground extraction used the pinned Python 3.12.14/pypdf 6.10.0 runtime
and four bounded workers. It decoded 95,091 physical pages, retained complete
page-text caches and per-page hashes, and completed all 400 cases with no
pending resources, original exception, persistence error or changed input.
It reused the old cover, consolidated-balance, currency and report-building
rules without edits. A current-only or January 1 comparative column did not
become an invented prior December 31 balance.

## Separate source checks and preserved checker failures

The separate checker imports no production parser, selector, account or scorer.
It reuses the pinned prior separate annual-assets checker for source identity,
financial-section boundaries, consolidated versus parent tables, exact amounts,
units/currency/CAS evidence, headers and period identities. This shared helper
uses pypdf; it is explicitly shared software, not independent decoding.

A second library, pdfminer 20251230, independently decoded 562 selected physical
pages. For every supported cell it matched the same asset-total row, both
literal monetary columns, their geometry and the dated or generic header.
The second library checks rows/headers; currency interpretation continues to
depend on the separate pinned native-source checker. All 472 cells passed.
The 110 unsupported cases retained their original status; additional cover
support from the checker did not promote a failed case or create a report.

Two failed QA attempts remain preserved. The first stopped after 81 cases:
SH600598 page 75 has a 2.0332-point difference between the label and amount
font midlines, despite over 81% vertical overlap. A regression test reproduced
the failure before requiring overlap of at least half the shorter character
box's height instead of a fixed two-point distance.
The second stopped after 170 cases: pdfminer represents SH601958 page 52's
leading digits with internal spaces. A second failing regression preceded
support for whitespace within syntactically valid decimal amounts. Exact
digits, two-column order, row identity, ambiguity and parent-table rejection
remain required. Both original checker versions, terminal failures and output
inventories are versioned. The third full QA completed all 400 cases. These
were QA executions; the original financial extraction ran once.

Every original PDF, source output, bound input and shared helper remained
unchanged through the final checks. This is same-researcher separate technical
QA, with two PDF libraries for selected rows/headers; it is not blinded review
or a complete visual examination of every original page.

The final local full suite passed all 1,193 tests in 18.872 seconds. Five
geometry regressions cover parent-table exclusion, different-row amounts,
duplicate matching rows, font-baseline drift and spaced monetary glyphs.

Published summaries are byte-identical to actual local outputs:

- [Extraction results](../../experiments/qlib/asset-expansion-2026-assets-results.json),
  SHA256 `9cc2ff170b414433941ebebc1c0bea4fd0d2e42ac916b7678e2b8a7653a36833`.
- [Final source QA](../../experiments/qlib/asset-expansion-2026-assets-source-audit.json),
  SHA256 `0d34300e257959d593fbe0d7e5a76391b0409ea30ad30e5bdba79ccfa4c341d0`.
- [All QA attempts and immutable inventories](../../experiments/qlib/asset-expansion-2026-assets-source-audit-history.json),
  SHA256 `a9c8f7d27f37d510ad1f4df4285557c81abf183779230c0255d8828c68e08171`.

## Required next gates

All PDFs were actually captured on October 23. At the frozen October 21 clock,
default observed-arrival visibility therefore exposes zero new reports.
Explicit reconstructed publication-day-end visibility exposes 290 supported
reports; it does not establish a historical feed, complete corrections or
investment admission. These aggregate counts are not monthly availability or
rankability counts. In particular, 182 paired editions do not imply 182
eligible securities at every formation.

Next freeze a source-only 2026 availability adapter that preserves the old
pre-2026 implementation and proves parity for its window. Select metadata by
fiscal year then publication, retain conflicting same-day editions, apply
both clocks and preserve newer failures without older-value fallback. Keep
the full initial 394-issuer cohort and the stale 2021 industry-vintage limits.
Bind every supported cell to the completed QA before later ranking.

Then freeze explicit 2026 formation/session/quote/corporate-action extensions
and the unchanged continuous physical account, including its December 31,
2025 denominator. Do not relax the 100-name coverage guard, decile/95% weights,
freshness, capital, cost or tax/allocation assumptions to fit later evidence.
Evaluate 2024 > 0, 2025 > 0 and 2026 January–October >= 10% together. October is
unfinished as of this run, and previously exposed 2026 evidence is not sealed.
