# Fixed12 original annual reports: capture complete, factor coverage insufficient

The investment objective remains the same frozen strategy and continuous account
with2024>0,2025>0 and2026January–October>=10%. This stage adds original source
coverage, not an investment return. No new2026 financial or market values were
read. October2026 is not complete as of this work.

## Actual execution and evidence

All requests were frozen and pushed before their respective acquisition or
numeric-inspection stages. There were no silent retries or source substitutions.

| Stage | Frozen commit / request SHA256 | Actual result |
| --- | --- | --- |
| Initial FY2022 metadata, published2023 | `0996dcb` / `b17246f79621f8581e2ff0c652643e7d51e46a0cb33a19329c1f04a210c58172` |12/12 POSTs succeeded; one initial full annual filing per issuer;23 unchanged inputs,65 outputs |
| FY2022–2024 annual PDF bytes | `69206e0` / `578b2a18c63944b3c833037608dd1beb493d2fb8a90b89570142b1f4b15ba18f` |34/34 fresh GETs succeeded; two authenticated cached originals reused;36 files;188174054 fresh bytes;96 unchanged inputs,178 outputs |
| Original narrow parser feasibility | `d5e7cba` / `eeb494305680daa0e4069dfe7f7343f8ed350d08b0437796036b567f067c229e` |36/36 classified;283 unchanged inputs,41 outputs; original parser and sources unchanged |

Public results and checks:

- [Initial metadata result](../../experiments/qlib/profitability-fixed12-initial-metadata-results.json)
  and [separate metadata audit](../../experiments/qlib/profitability-fixed12-initial-metadata-audit.json).
- [PDF capture result](../../experiments/qlib/profitability-fixed12-annual-pdf-results.json)
  and [separate byte audit](../../experiments/qlib/profitability-fixed12-annual-pdf-byte-audit.json).
- [Full schema coverage](../../experiments/qlib/profitability-fixed12-schema-results.json)
  and [run integrity check](../../experiments/qlib/profitability-fixed12-schema-run-integrity.json).
- [Selected original page review](../../experiments/qlib/profitability-fixed12-source-page-review.json),
  with document identity, physical page number and local rendered image SHA256.

The last integrity check is stdlib-only and imports no production module. It
rehashes all283 inputs and41 outputs, reconstructs summary counts from36 packets,
checks successful terminal/input journals and enforces empty observations for
rejected sources. It was authored after the run by the same researcher. It does
not independently authenticate PDF text, fiscal cells or accounting comparability.

## Complete coverage, including failures

The fixed12 were inherited from an earlier source sample, without selecting by
new returns. They are not an investable universe. All12 remain in the inventory.

| Issuer | FY2022 | FY2023 | FY2024 |
| --- | --- | --- | --- |
| SH600166 | parsed | parsed | parsed |
| SH601108 | schema unsupported | identity unverified | identity unverified |
| SH600901 | identity unverified | identity unverified | identity unverified |
| SH603517 | schema unsupported | identity unverified | schema unsupported |
| SH600418 | schema unsupported | schema unsupported | schema unsupported |
| SH600655 | schema unsupported | schema unsupported | schema unsupported |
| SZ000825 | identity unverified | identity unverified | identity unverified |
| SZ000783 | identity unverified | identity unverified | identity unverified |
| SZ000750 | schema unsupported | schema unsupported | schema unsupported |
| SZ000933 | identity unverified | identity unverified | identity unverified |
| SZ002372 | schema unsupported | schema unsupported | schema unsupported |
| SZ002925 | identity unverified | identity unverified | identity unverified |

Thus3 parsed reports produce6 fiscal-column observations;15 schemas are
unsupported and18 cover identities unverified. Only one issuer has all three
reports parsed. Every parsed report remains pending complete numeric visual review;
no factor or backtest source has been admitted.

## What selected original pages establish

Seven physical pages across six reports were rendered and visually inspected.
This is a diagnostic selection after the full fixed36 run, not a coverage claim.
The page-review artifact records the full source SHA256 and announcement ID.

- SH600166 FY2022, physical124: the supported income table has explicit RMB/yuan
  units and two fiscal columns. This inspection alone does not authenticate all
  assets or other supported report cells.
- SH603517 FY2022, physical81 and84: two fiscal columns are present; the balance
  dates wrap across text lines, and note references use Chinese parentheses.
  These differ from the strict one-line header / note grammar. They are not
  missing numeric data and must not be treated as a third fiscal column.
- SH600418 FY2022, physical78: note references use Arabic parentheses. The
  consolidated statement also contains insurance lines; syntactic extraction
  alone cannot certify economic comparability for a gross-profit factor.
- SZ002372 FY2022, physical80 (printed79): numbered consolidated heading, no
  note column in the header, and explicit RMB evidence in the local financial
  section rather than the original parser's exact unit-line format.
- SH600901 FY2023, physical2: the literal securities-code label uses a vertical
  separator, which the first-five-page matcher does not support.
- SH601108 FY2022, physical141: the broker table reports net interest/fee income
  and operating expenditure, not the literal revenue/cost-of-sales pair required
  by this prototype. No total-expenditure or net-profit proxy was substituted.

An additional bounded text inspection of FY2023 first-eight pages found literal
codes on physical6–8 for several reports rejected by the first-five-page rule.
This does not authenticate the remaining18 identities or justify accepting every
document. No source amount, issuer or failed case was changed.

## Verification and next bounded step

Local full suite:972 tests passed. Four new integrity regressions cover a complete
all-rejected run without data admission, a false summary observation count, a
rejected packet emitting observations, changed bound input and path escape.
They use synthetic journals, not original-PDF authenticity evidence.

The schema freeze CI [39657245782](https://github.com/shouldnotappearcalm/stock-rsi-lab/actions/runs/39657245782)
passed all three jobs: Python3.11, Python3.12 and research dependencies. The two
preceding capture freezes also passed all three. Check the latest push separately;
an earlier green run does not certify later code.

Preserve this immutable run. The next parser must be a separate version with
bounded grammar, real-source excerpts and negative cases for wrong fiscal
columns, parent/consolidated confusion, missing rows, ambiguous units and extra
values. Candidate grammar extensions are numbered headings, multiline fiscal
headers, explicit note references, literal identity separators and a bounded
first20-page identity window. Broader unit/currency scope needs explicit local
evidence. Duplicate headings, financial statements without the required fields,
and accounting incompatibility remain explicit failures; no best-performing
subset or guessed values.

Even improved parsing would leave correction/version-history completeness,
historical nonfinancial universe coverage and accounting compatibility unresolved.
Actual2026 capture times also cannot certify observed historical2024/2025 arrival;
publication-day-end reconstruction remains conditional. Resolve these source
contracts before registering one profitability candidate with its controls and
2024/2025 continuous-account gate. Only an unchanged passing candidate can receive
a separately frozen2026 diagnostic. The original three return conditions remain
unproven; earlier failed strategies and fractional-share envelope results stand.
