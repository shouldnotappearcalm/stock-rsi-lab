# Separate source grammar V2, same36 original annual reports

The objective remains2024>0,2025>0 and2026January–October>=10% in one continuous
account with a frozen strategy. This is source extraction work only, motivated
by seven visually checked original pages, not any new return or2026 market fact.

Preserve all old source files, original narrow parser and its3/15/18 supported/
unsupported/unverified classifications. The new module is
`src/stock_rsi/annual_profitability_v2.py`; the runner is
`scripts/inspect_profitability_fixed12_v2.py`. Before a full36 run, freeze/push
`experiments/qlib/profitability-fixed12-v2-request.json` with all source, method,
old-run, review, real-excerpt and regression-test hashes. Source selection remains
exactly fixed12 × FY2022/2023/2024. No network, financial proxies, price/return
reading, stock ranking, universe selection or account execution is permitted.

## Bounded new grammar

- Identity code evidence: first20 physical pages, exact six-digit tokens after
  literal company/stock/security-code labels with optional colon or vertical bar.
  All such codes within that window must agree with the expected code. Preserve
  original matching text/page. Keep the first-five-page annual-title rule and
  numeric/line boundaries. A code appearing only outside the window is unverified.
- Statement headings: original exact consolidated/parent names, optionally
  prefixed by one/two Arabic digits and an enumeration separator. Still require
  one unique ordered consolidated/parent pair and at most five physical pages.
  Duplicate statement sets and unrecognised boundaries fail.
- Fiscal headers: exact current/prior annual order and two fiscal columns;
  optional note-column label; at most four contiguous text lines on one page.
  Additional fiscal/header lines, reversed dates and extra monetary cells fail.
- Notes: optional explicit Chinese chapter/Arabic reference, or Chinese/Arabic
  parenthesised reference after a Chinese chapter label. Do not strip arbitrary
  tokens or choose the last two numeric values.
- Units: retain original explicit table CNY units (yuan or ten-thousand yuan).
  A bare unit line is supported only with one matching explicit RMB financial-
  section unit sentence in the three immediately preceding same-page lines
  before the statement heading. No report-wide currency guessing or cross-page
  unit carry. Preserve literal evidence/scope/page and multiplier.
- Fields stay literal consolidated revenue, cost of sales and total assets.
  Preserve both fiscal columns and original field provenance. Never substitute
  total expenditure/cost, net income, parent assets or a current-vintage API field.

## Tests, source run and limits

Real regression fixture uses sparse literal lines from SH603517 FY2022 physical
pages81/82/84/86; all full-page text hashes match the old frozen run. Numeric
expectations come from the original visually checked balance/income pages81/84.
CI does not fetch/authenticate PDFs or prove completeness from sparse excerpts.
Synthetic tests cover numbered headings, explicit local currency, notes, reversed/
extra columns, financial proxy rejection, duplicate boundaries, missing values,
bounded/conflicting identities, unchanged observed/reconstructed visibility and
future payload isolation. Runner tests cover classifications remaining unadmitted
and interruption retaining original error, pending cases and post-run hashes.

Run the full unittest suite before actual source processing. The existing PDF
runtime pypdf6.10.0 and1200-page cap stay fixed. Use one new directory
`gross-profitability-fixed12-grammar-v2-20261022`; never overwrite/resume old runs.
Every report emits status, original identity, new parser contract, literal identity
evidence, all page-text hashes and either two source observations or exact error.
Unexpected PDF/runtime error aborts, preserving partial cases and original error.
Rehash every bound input and request even after interruption. A changed input or
failed terminal persistence prohibits a success summary.

The summary retains all36 cases/12issuers, old/new counts, every status transition
and all-year per-issuer source coverage. Parsed observations remain pending full
visual/accounting review. Financial-version/correction history, economic sector
compatibility, historical arrival and investment-factor admission remain false.
The fixed12 sample is not the investment universe. A syntactic improvement cannot
establish an investable gross-profitability factor or a qualifying strategy.

After the run, inspect newly supported raw evidence before separately defining
the next accounting/history/universe coverage action. Keep all failed sources,
including brokers and mixed financial statements, with no outcome-selected subset.
Actual2026 capture still cannot be backdated as observed2024/2025 arrival; an
explicit reconstructed publication-day-end scenario remains conditional. Any
later strategy, controls and2024/2025 selection must be frozen before outcomes;
2026 remains a separate unchanged-candidate diagnostic, never method feedback.
