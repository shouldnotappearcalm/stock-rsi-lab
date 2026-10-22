# Gross-profitability primary rejected on2024 development

The single registered high-GP/assets candidate failed its2024 positive-return
requirement. At40bp additional per-side cost it returned-7.5704% in2024 and
+5.2012% in2025,with91.2757% average exposure and zero unverified held marks.
Two-year compound return was-2.7629%. No development lead was selected,no raw
confirmation was initiated and no2026 diagnostic was run. This does not achieve
the user's2024>0,2025>0,2026January–October>=10% objective.

## Frozen scope and actual results

Request SHA256`b8dded6ac3fbeeda528b43004cf9eb513171f61dd6d93b11fe738109e19da5b5`
was pushed in`37307e9d30042fa31b3cad098195373e3a1ce20a` before any real ranks
or returns. That commit's hosted CI run39697823953 passed all three jobs.
The pre-freeze full suite passed1119 tests; after separate checker regressions,
the final full suite passed1124. No dependencies were installed.

The actual strategy run executed once,with one primary and two diagnostic
controls at20/40bp additional costs. Each uses a continuous CNY1000000 account
over485 actual sessions,2024Jan2–2025Dec31,with no annual reset. All quote values
were physically capped at2025. Only the fixed primary at40bp could become a
development lead; controls were not alternative candidates.

| Extra per-side cost | Portfolio |2024 net %|2025 net %|Two-year net %|Average exposure %|Unverified held marks|
| --- | --- | ---: | ---: | ---: | ---: | ---: |
|20bp|High-GP primary|-7.1387|5.4533|-2.0747|91.2240|0|
|40bp|High-GP primary|-7.5704|5.2012|-2.7629|91.2757|0|
|20bp|Eligible equal-weight control|6.1298|19.0130|26.3083|69.9964|1|
|40bp|Eligible equal-weight control|5.7356|18.7640|25.5759|69.8905|1|
|20bp|Low-GP control|11.2917|28.3957|42.8937|93.8211|0|
|40bp|Low-GP control|10.8178|28.0524|41.9048|93.8763|0|

The broad control's realized exposure is about70%,despite95% target weights:
many small per-name allocations face100-unit lot sizing/minimum-cost effects
at this capital. It also has one unverified held mark. Do not treat that control
as a fully invested/risk-matched benchmark or waive its mark because it is
profitable. Low-GP performed better in these development years,but the frozen
protocol prohibits promotion of a diagnostic control. This run does not turn
that observed control into a tested investment recommendation or2026lead.

Monthly eligibility varies179–247 names. Every initial394 source issuer remains
in each of24 formation receipts,with explicit nonmember,source-vintage financial/
unknown,latest-report failure,freshness or quote exclusions. A direct membership
source check confirms that the394 Jan2 start-cohort identities exactly equal
the preceding2023Dec29 formation-date mainboard identities; no additional name
enters from that one-session date difference. Measured historical constituent
announcement/arrival times remain unverified.

## Separate source/normalized-account audit

The separate checker imports no production selector,quote reader or ledger.
It independently checks9456 cohort/formation rows,5089 exact source GP ratios,
24 primary/control target sets and per-formation persisted artifacts. Native
binary scalar seeks independently read113259 distinct pre2026 quotes. The
checker verifies all7599 signed simulated order records and233461 holding rows
across six continuous accounts:daily-open fills,declared costs,normalized
inventory,cash flows,holding marks,NAV,year boundary returns,exposure,drawdown,
turnover and missing-mark status. All18591 input bindings including the request
and79 output files remain unchanged through actual execution and QA.

The checker does not independently reimplement prior-close lot sizing or
reextract all annual PDFs. Prior-close sizing has the runner's account-clock
checks and behavior regressions; source values/version choices retain their
previous separate source audits. This is same-researcher after-outcome QA,not
blinded review or raw-share/intraday execution validation. Reconstructed annual
arrival,stale2021classification,current business/reporting compatibility and
complete corrections remain explicit limitations. All admission flags stayfalse.

## Retained initial checker failure

The first full QA failed at its assumption that indicator quantities were
unsigned and could not exceed requested normalized units. Inspection of the
installed pyqlib0.9.8 sources showed that report.py exports signedamount_delta/
deal_amount_delta and exchange.py rounds using
`floor((amount*factor+0.1)/100)*100/factor`. The source-unit tolerance can create
a small normalized excess when formation and execution factors differ.

The correction uses signed deltas for inventory and enforces the exact engine
lot rule plus its0.1 source-unit bound,rather than accepting arbitrary overfills.
It also checks full odd-lot sell exits and cash-limited buy lots. Across all six
accounts1274 orders round above the request; maximum excess is0.09819905 source
units,within the documented engine bound. This is not evidence of valid raw
share execution. Both original library files,initial checker and failed log are
retained with hashes. Negative and positive regressions cover signs,offsets,
future tails and the exact rounding exception.

Actual strategy runs:1. Actual full-QA attempts:2,firstfailed/secondpassed. No
frozen signal,runner,request,source or simulation output was modified or rerun
to satisfy the checker. The unfrozen request draft before pre-freeze metrics
validation is separately retained locally; no real ranks/returns existed then.

Public byte-identical actual outputs:

- `gross-profitability-pre2026-results.json`,SHA256
  `5b632615a5702f9518769aa0a4e294838504fa7284ee5a82fcb3ccd0ab061792`.
- `gross-profitability-pre2026-audit.json`,SHA256
  `6fc8fe62e1add32ccdf32c96045dfeae727ab54086ae94bdbd6997b5c2b4d551`.
- `gross-profitability-pre2026-checker-history.json` retains failure/correction,
  source and validation log digests. Raw full outputs remain local.

Reject this registered primary. Continue with a separately motivated hypothesis
and a new transparent development budget; do not rewrite this trial,select a
2026winner from it or relabel a control as its primary. The original economic
objective remains active and unachieved.
