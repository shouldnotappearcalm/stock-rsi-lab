# Standalone annual total-assets source extraction

The high-GP primary failed2024 and remains rejected. The next investigation is
annual asset expansion,not promotion of its low-GP diagnostic control. The
economic objective remains one frozen strategy/continuous account with2024>0,
2025>0 and2026January–October>=10%,without2026 method feedback. This phase only
extracts source fields; it registers no investment rule,rank or account.

## Scope and bounded change

Reuse all1236 original annual editions over the full dated394 issuer range,
including every old failure and financial/unknown-sector issuer. Do not choose
the791 successful GP reports or220 three-year successes as a stock universe.
No network,install,new PDF text decoding,price feature read,return computation,
asset-growth ratio or2026 financial/market input. Existing authenticated408
initial/828 later page-text caches are the only new parsing input.

`src/stock_rsi/annual_assets.py` reads consolidated total assets independently
of income revenue/cost numeric rows. It reuses unchanged V7 header/cell grammar,
original physical page/row/header/unit/currency evidence and full-report primary
financial-section boundaries. Where that primary section exists,its ordered
balance/parent/income-title context remains a structural requirement; this is
not an unrestricted arbitrary-table extractor. The new conflict check is scoped
to the balance table rather than income-table local units. Global explicit
foreign reporting currency still fails. Explicit CNY or the same registered,
quoted CAS19 regulatory inference remains necessary; it stays labelled as
inference rather than a literal currency quote.

Only the literal资产总计 row is extracted,with positive exact monetary values
and explicit元/万元 conversion. Parent-only substitution,missing/reversed/
third columns,duplicates,unknown currency and invalid amounts fail closed.
Explicit current/priorDecember31 yields both dates. Explicit currentJanuary1
opening yields current only. Generic期末余额/期初余额 needs the existing unique
same-page currentDecember31 anchor and yields current only; its opening date
stays null. No preceding year is assigned to an undated opening column.

One immutable asset report holds the coherent balance cells of one original
annual edition,PDFhash,announcement ID,report year,publication-day end and actual
observed arrival. Cells keep literal/header/page/unit/source metadata and column
roles; no cross-document financial cell mixing. Record digests include the
payload. Default OBSERVED visibility requires actual arrival as well as public
content; before admission do not inspect/hash future payloads. Explicit
RECONSTRUCTED_PUBLICATION_DAY_END is a conditional content reconstruction.
The source helper returns all visible supported editions,not a latest-report
eligibility decision. Any later strategy must still consult the full case
inventory so a newer unsupported/ambiguous edition cannot be skipped.

## Protected controls and source runner

All791 V7 GP-supported reports/1243 existing total-assets cells are reused
verbatim,including legacy parser-contract/evidence fields. Only the new outer
one-field report contract changes. Their source GP record IDs and parent case
file hashes stay recorded. The old GP parser,requests,outputs and failed trading
experiment remain unchanged. No previously supported asset is reparsed to a
different value or lost.

The385 GP-schema failures with verified cover identity receive balance-only
inspection from authenticated original text. All60 identity failures stay
unverified without numeric admission. Per-page hashes/cache extractor identity,
original PDF hashes and old case identities must agree before parsing. Cache
authentication errors are unexpected hard failures,not ordinary schema failures.
Expected unsupported source formats retain original exception type/message and
an empty asset report in the complete case ledger.

`scripts/inspect_annual_assets_source.py` uses four foreground worker processes,
four maximum outstanding reports and deterministic result persistence order.
Each completed case is written once. No overwrite/resume. On an unexpected
error/interruption,retain the completed prefix,submitted keys,pending cases,
original exception and all input/request post-hashes. Source/request mutation
or persistence failure prevents a successful summary. A previous failed output
must not be replaced with a successful retry in the same directory.

Freeze/push`experiments/qlib/annual-assets-all1236-request.json` before complete
balance-only corpus inspection. Bind the complete V7 original-source input and
1550-output closure,its independent audit/request,full original annual metadata,
membership/cohort,new code/tests/this plan. Source runtime is existing Python
3.11.15; previous text extractor identity remains pypdf6.10.0 in the authenticated
caches. No new extractor/runtime installation is needed.

Expected1242 local outputs:1236 case files,input-before,case_results,
visibility-checks,input-postcheck,terminal,summary. Four year-end2024/2025
observed/reconstructed source checks retain record IDs/counts; they are all-
edition views,not ranked or latest-eligible pools. Default observed historical
counts must be zero. All incomplete sector/business/version/accounting/
investment claims remain false.

## Verification and next stage

Tests first cover income independence,exact consolidated rows/units/columns,
generic date anchors,explicitJan1,ambiguous/foreign/extra-column rejection,
scoped CAS inference,coherent record digests,visibility boundaries and hidden
future payloads. Runner regressions cover protected old cells,both cache
locations,current-only generic opening,retained identity failures,fresh-only
output,cache corruption,source/request mutation and original interruptions.
Run full unittest discovery before the freeze,then execute the registered source
run once in foreground.

Afterward independently compare all791 reused reports/1243 cells to V7 and
source-check every newly supported balance cell/date/header/unit against the
original PDF pages with a separate checker. It must not import the new source
parser or constructor. Disclose shared researcher/PDF engine and incomplete
manual review. Preserve failed QA attempts. Rehash the complete input/output
closure and publish derived counts/checks; keep originals/full source payloads
local. Then establish formation-specific latest annual asset availability and
freeze a single asset-expansion hypothesis and missing-data/control budget
before any2024/2025 asset-growth ranks or returns. No2026 diagnostic is admitted
by this source phase.
