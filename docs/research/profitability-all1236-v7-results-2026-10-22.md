# V7 annual-source header inspection and separate QA

V7 completed the same1236 original announcements and dated394 source-issuer
range. Supported reports increased665→791; schema failures385 and identity
failures60 remain explicit. No investment strategy/ranking/account/return was
run. The objective remains2024>0,2025>0,2026January–October>=10%,one frozen
strategy/continuous account,no2026 method feedback. October remains incomplete.

The frozen request SHA256 is
`51d047df56f4150906172d3ac27972ee3167e9b98cb4b1b32e800d066099eb55`,pushed in
`ddf66f22c1ab7829e5bc7d6a1f90eeb7c5e1e7ee` before V7 full-corpus numerical parsing.
That exact commit's three hosted CI jobs passed in run39691179151. Local full
unittest discovery passed1076 before the freeze and1080 after the separate QA
regressions were added. No package installation or dependency-list workaround.

## Actual source coverage

| Fiscal year | Supported | Unsupported schema | Identity unverified |
| --- | ---: | ---: | ---: |
|2022|264|128|20|
|2023|263|126|22|
|2024|262|127|18|

Older reissued fiscal years remain in the full corpus. SH has450 supported,
207 schema and36 identity cases; SZ341/178/24. The corpus contains1243 annual
observations across282 issuers.220 have supported current-year reports for all
2022/2023/2024,up from126. Neither220 nor282 is an admitted investment universe;
all394 source issuers and missing report editions remain represented.

The single actual source run reused the authenticated408 initial and828 later
whole-report text caches; no PDF text was re-extracted in that run. It produced
1550 immutable files,checked12760 input bindings including its request before
and after processing,and preserved every complete observation from all665
previously supported reports identically. Old source files,requests,parsers,
failed accounts and V6 results are unchanged.

## Date and header semantics

The126 newly supported reports include107 generic balance headers with an
unresolved opening date. Each current balance column has an explicit same-page
report-yearDecember31 statement-date quote before the literal期末余额/期初余额
header. The mapping is labelled as a semantic inference; the header is not
rewritten to contain dates. Opening fiscal dates remain null and no comparative
annual observation is generated. Explicit Jan1 also remains current-only.

Other extensions handle bounded same-page split headers,note-chapter labels and
identical headers repeated on later consolidated continuation pages. Current/
prior ordering,consolidated-before-parent scope,three literal fields,existing
row/money grammar,CNY/unit evidence and original availability contracts stay
fixed. No integer-cell/proxy/unknown-currency fallback or2026 investment input.

## Separate source QA

The separate checker passed all1236 source/case/hash and old-observation checks.
For the126 new reports,it directly redecoded1129 original PDF pages and checked
420 literal monetary cells,dates,headers,units and reporting-currency evidence.
Exact rational arithmetic confirms normalized amounts. It explicitly checks
current-only generic dates and rejects fabricated comparative records.

The checker reuses previous separate QA helpers,shares pypdf6.10.0,and was
written by the same researcher after source execution began. This is not a
blinded or full independent grammar replication,all-page independent extraction
or complete manual numeric visual review. Those limitations stay explicit.

A negative regression caught the checker's non-overlapping substring count:
two adjacent identical date anchors could count as one. It was corrected to
count all source-line windows before the first actual source QA. The failing
regression log,passing full suite and actual QA log are retained and hashed in
`profitability-all1236-v7-checker-validation-history.json`. No frozen source
parser/output was changed to pass the checker. Actual source execution and
actual full-source QA were each run once.

Public`profitability-all1236-v7-results.json` and
`profitability-all1236-v7-source-audit.json` are byte-identical copies of actual
local outputs. Sources/text/renders remain local. Summary SHA256:
`407404c01b2e703055b17b2fbfe05d80558099ad3d64c6050210992c3ba3f9d3`.
QA SHA256:`706c383c92fc490684c3b9b245019f84194031a6c2a43304a34bfa3a6eda1864`.

## Remaining work toward an investment test

Source parsing is not economic validation. Historical captures are2026 arrivals;
observed mode does not make them visible in2024/2025. Publication-day-end mode
remains an explicit conditional reconstruction. Full revision history,
nonfinancial/business/accounting compatibility and numeric visual review remain
unverified; all factor-admission and profitability-completion flags remain false.

Next establish publication-visible nonfinancial identity and accounting/version
rules over the full dated source range,then freeze one GP investment/missing-data
protocol and equal-budget2024/2025 continuous-account development. Do not choose
the three-year parse-success subset as a stock pool or use2026 outcomes to
change the method. Raw-share/intraday confirmation precedes any unchanged2026
diagnostic; no return objective has been proved by this source stage.
