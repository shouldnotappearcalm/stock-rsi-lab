# Profitability source pilot: real filing vintages replay correctly

The source-only pilot passed. It produced four fiscal observations from two
previously selected original annual reports, checked12 literal amounts and16
historical snapshots. This is one issuer's data feasibility evidence. No security
ranking, strategy account or investment return was computed. The objective
2024>0,2025>0,2026January–October>=10% remains unproven.

## What became usable

`annual_profitability.py` parses three explicit consolidated statement rows,
retaining original filing identity, period column, currency unit, physical page
and source row. Its snapshot function keeps the latest visible publication for
each issuer/period, with conflicting same-day versions rejected. The new module
can supply source-level annual gross-profit-to-assets observations to a future
separately registered profitability experiment. Full investment-universe and
accounting compatibility checks are still required.

The2013 primary-paper formula was checked on physical pages1/3 of the published
paper PDF. The file was retrieved from a mirror; the author university biography
and NBER abstract corroborate publication identity. This pilot does not claim
full paper replication or a China long-only performance result.

## Actual source regression

The same2023 fiscal cost-of-sales row has two disclosed vintages:

| Source report | Publication day | 2023 consolidated cost of salesCNY |
| --- | --- | ---: |
| Original2023annual report | 2024April27 | 49,712,583,057.97 |
| Comparative column of2024annual report | 2025April26 | 49,997,740,569.45 |

The second report's physicalpage156 explains theCNY285,157,511.48 reclassification
from selling expense into cost of sales for2023. In this two-document subset,
the later comparative value appears only after that later document is visible;
it cannot replace the earlier observation in a2024 snapshot. The subset does not
establish the first public appearance of the change: other announcements and
interim corrections have not all been collected. Presentation changes also
limit economic comparability of raw profitability ratios across years/firms.

The denominator comes from consolidated total assets, not the parent-only asset
statement. Income uses营业收入/营业成本, not total operating cost or net income.
No raw values are rounded to a preferred interpretation, filled with zero or
selected by their effect on returns.

## Observed versus reconstructed availability

Default`OBSERVED` mode admits information only after both the conservative end
of the publication day and the actual capture time. The PDFs were captured in
October2026, so all eight2024/2025 default observed queries are empty. The fiscal
period and nominal disclosure date do not override that capture boundary.

Explicit`RECONSTRUCTED_PUBLICATION_DAY_END` mode admits a conditional observation
after23:59:59.999999Shanghai on the publication day. Eight additional queries
check pre-publication, same-day and later observations. Adding the second filing
does not change the2024 year-end snapshot. Reconstruction does not certify actual
historical data arrival. These are analysis instants, not invented trading sessions.
The2022 comparative column first obtained through the2023 report cannot supply
an initialJanuary2024 state; original2022 filings remain necessary.

## Authentication, arithmetic and regression coverage

Methods and source request were pushed at`6a3e488` before fixture creation; that
commit's Python3.11/3.12/research CI jobs passed. Request SHA:
`e90736a8666cb7a147c899d6775ff3a9223ce0b9bd356374ee3aeba9953d9e6a`.
The actual run exited0; all33 bound inputs, including the request, rehashed
unchanged. Seven local output files retain observations, snapshots, all extracted
page-text hashes, input-before/postcheck, terminal and summary. Original PDFs,
old strategy methods, accounts and failure evidence remain unchanged.

A separate source-page/arithmetic script imports no production modules. It checks
all12 amounts directly on the curated original PDF pages, independently computes
ratios withFraction andDecimal60, reconstructs all16 snapshots, checks all33 input
hashes before/after and all seven output hashes. It shares pypdf6.10.0 with the
runner, and was authored after the source fixture existed; this is a separate
implementation, not a blinded independent-researcher audit. The final run passed.
Its report SHA is
`31dc1674d0d40e5aa4da1ef7972de67893eec540406d56f0cc1e2904a2532faa`.

A small public real-row fixture retains source URLs, PDF hashes, physical page
numbers and relevant literal header/row excerpts. CI can continuously regress
column/row/unit handling and original-versus-comparative visibility. CI does not
fetch/authenticate the complete original PDFs, prove financial-version
completeness, or certify historical arrival. All four real observations are exactly recreated from the public excerpts. The
final local full suite passed951 tests. Synthetic cases separately check
unknown units, wrong currency, parent statements, ambiguous rows/columns,
nonfinite/empty amounts, source/request mutation and interrupted extraction.

## Next work toward the investment objective

Expand original filing coverage to the preexisting fixed12issuer source sample,
including initial2022 originals, metadata/corrections and accounting compatibility,
under a new bounded capture request. This remains a source sample, not a stock
selection universe. Historical nonfinancial identities and sufficient full-universe
coverage must precede candidate ranking. Then separately freeze one investment
rule, budget, comparison/control and2024/2025 continuous-account gate. Only after
passing that gate may the unchanged candidate get a frozen2026 diagnostic.
No2026 financial/market/return values were used in this pilot.

Evidence:

- [Source plan](gross-profitability-source-plan-2026-10-22.md)
- [Frozen request](../../experiments/qlib/gross-profitability-source-request.json)
- [Original-page review](../../experiments/qlib/gross-profitability-source-review-2026-10-22.json)
- [Summary](../../experiments/qlib/gross-profitability-source-results.json)
- [Separate source/math audit](../../experiments/qlib/gross-profitability-source-fixture-audit.json)
- [Run verification](../../experiments/qlib/gross-profitability-source-run-verification.json)
- [Versioned real-row regression](../../tests/fixtures/annual-profitability-real-row-vintages.json)
