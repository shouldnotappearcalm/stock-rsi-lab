# Same36 annual source reports: bounded issuer, statement and currency context V3

The goal remains one frozen strategy/continuous account with2024>0,2025>0 and
2026January–October>=10%. V2 improved supported source reports3→8 and independently
checked48 literal amounts, but does not supply an admitted investment universe.
This step is another source-data repair, without stock ranks, prices or returns.

## Evidence before code freeze

Read only the same previously authenticated pre2026 annual filings. Eight source
documents were inspected for format context; extracted pages remained private.
Six original pages were visually checked, with original PDF and rendered-page
hashes in `profitability-fixed12-v3-source-context-review.json`.

- SH600655's cover identifies the issuer; later other-company codes are context,
  not proof of a different report subject.
- SH603517 FY2023 physical7 identifies the issuer in a stock-information table;
  its stock-code label and value are not adjacent in extracted text.
- SZ002372 FY2022 physical80 explicitly declares RMB/yuan in the primary financial
  statements section; later tables within that section have bare yuan unit lines.
- SZ000933 FY2022 physical100 explicitly declares both the currency used to
  prepare these financial statements and RMB/yuan normalization. A mere functional-
  currency sentence is a different claim and cannot substitute for this evidence.
- SZ002925 FY2022 physical146 shows normal two-column source geometry whose text
  extractor places the title/year/amount cells on successive lines. Currency
  evidence is still separately required; this page alone says only yuan.
- SZ000933's balance header is2022Dec31/2022Jan1. Do not relabel its opening
  balance as2021Dec31 or combine it into a synthetic prior-year GP observation.
  The three current-year source cells are valid source-extraction targets.

## Exact separately versioned contract

Preserve all old/V2 code, sources, results and failures. New module:
`src/stock_rsi/annual_profitability_v3.py`; runner:
`scripts/inspect_profitability_fixed12_v3.py`. Freeze and push
`experiments/qlib/profitability-fixed12-v3-request.json` before the full36 run.
Bind source/method dependency closure, old results/audit, new tests/real excerpt,
plan, source-context review and six reviewed PNG identities. No new network.

Identity uses direct code evidence in first-five-page cover context first; a wrong
explicit cover code cannot be rescued by an expected code elsewhere. If no cover
code is found, require bounded first20-page issuer/company-information context or
the exact issuer stock-table header and one six-digit A-share code. Retain other
literal codes for diagnosis. Annual-title matching permits spaced year/title
glyphs within the first five pages; it does not drop the report-year check.

Primary financial statements are bounded by one exact `二、财务报表` and the first
explicit end heading (`三、公司基本情况`, `三、财务报表附注`, or `财务报表附注`), at
most40 physical pages apart. Require unique ordered consolidated/parent balance
and income headings within that section. Later note-table headings are outside
the section; do not choose the first of ambiguous main statement sets. Without
a primary-section marker, retain global unique-boundary requirements.

Currency is either literal table RMB/unit, one explicit RMB/unit declaration at
the primary-section beginning, or the reviewed explicit report-preparation
currency/unit sentence. Bare table unit must match the declaration. Functional
currency alone, random RMB transaction amounts, outside-section unit sentences,
contradictory/multiple declarations and guessed default currency fail. Preserve
literal evidence and source pages/scope in every affected cell.

Remove blank lines without reordering source tokens. Join a split numeric heading
prefix only with an exact financial-statement title on the same page. Header
matching permits at most eight contiguous nonempty same-page lines; row matching
at most four. Keep exactly two monetary cells and explicit note grammar. Missing,
extra, cross-page and duplicated rows fail; never borrow a number through another
row label or choose the last two numbers. Preserve normalized literal row blocks,
source pages, header labels and hashes. Unknown units/extra fiscal columns fail.

Ordinary prior-Dec31 balance headers retain current and comparative observations,
including all existing V2 records. A balance comparison labelled current-Jan1
emits only the complete current-year record; the opening date and both literal
row amounts remain evidence. No prior-year GP is fabricated from mismatched as-of
dates. This follows the factor's current annual revenue/cost/assets definition,
not any strategy result. V3 does not add a portfolio or select an investment rule.

## Execution, regressions and remaining gates

Run all repository tests before actual source processing. Preserve pypdf6.10.0,
1200-page cap and the same36 document identities. Use a new fixed fresh directory
`gross-profitability-fixed12-source-context-v3-20261022`, no overwrites/resumes.
Retain all36 case packets and transitions from V2, full-page text hashes, exact
errors, observations, input-before/postcheck, terminal and summary. Rehash all
bound inputs/request after processing or interruption. Runtime error/input change
or loss/change of any supported V2 fiscal cell/coordinate prohibits success;
preserve completed cases and original error. Summary records current-only opening-
balance cases explicitly. No silent comparison-column date conversion.

Tests include old real-source numeric preservation, the new real preparation-
currency/current-source fixture, scoped duplicate notes, issuer cover precedence,
issuer stock table, currency evidence rejection, bounded vertical rows/headers,
opening-date isolation, missing/duplicate/main-scope failures and interrupted run.
CI checks sparse excerpts, not original PDF authenticity or complete accounting.

Source/financial-version history, arrival, accounting comparability and investment
factor admission remain false. An eventual historical research run must state
its reconstructed publication-day-end assumptions. Do not imply observed2024/2025
arrival from2026 capture. Historical nonfinancial identities and wider whole-
universe source coverage remain separate work before a frozen profitability
candidate and2024/2025 development controls.2026 remains an unchanged-candidate
diagnostic, not method feedback; October2026 is not complete yet.
