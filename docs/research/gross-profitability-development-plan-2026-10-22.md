# One conditional gross-profitability development screen

The objective stays one frozen strategy/continuous account with2024>0,2025>0,
and2026January–October>=10%,without method feedback from2026. Previous source
phases are complete; this experiment tests a single economic hypothesis rather
than selecting another parser-success stock pool. No2026 prices,financial
values,sector winners or strategy returns inform its design.2026 was previously
exposed and cannot become a fresh sealed test by renaming it.

## Hypothesis and deliberate evidence boundary

Novy-Marx2013 proposes consolidated gross profit scaled by book assets as a
productivity proxy. The archived original paper's page3 defines revenue less
cost of goods sold and discusses nonfinancial scope,June-lagged annual data and
industry-demeaned variants. This experiment is a long-only A-share adaptation:
营业收入 minus营业成本 over资产总计,using the latest public-day-end-visible
current annual report,monthly equal weights and an archived2021industry screen.
It is not a replication of the paper or a verified PIT investment study.

Current evidence cannot certify complete correction histories,current business
identities or uniform expense classification. The original SH600166 report's
warranty-cost reclassification is already known and remains unchanged in its
published versions. Do not invent an adjustment or backfill a later comparative
into an earlier date. The2021sector classification is explicitly stale; numeric
support is selective and may bias results toward reporting conventions.

Earlier source plans required stronger business/accounting/version evidence
before investment validation. This plan explicitly permits a conditional daily
engineering screen before that gate,to reject weak hypotheses without requiring
complete held-name raw-source capture first. It does not relax the later gate
or admit the factor as verified research. A positive screen requires targeted
business/accounting/version investigation and raw-share account confirmation;
neither source counts nor daily proxy returns can satisfy the user's objective.

## Fixed candidate and universe

One candidate:`gp_assets_top_decile_conditional`. The two descriptive controls
are`eligible_equal_weight` and`gp_assets_bottom_decile_control`; controls cannot
be promoted as replacement candidates after seeing their outcomes. Candidate
budget1,no parameter grid,no price/momentum/sector override,one continuous
CNY1000000 account per profile,without annual resets.

The initial source range is the394 mainboard CSI500 constituents recorded asof
2024Jan2,not220 three-year parse successes. At each formation,intersect this
fixed historical starting cohort with membership intervals visible under the
existing reconstructed constituent source. Newly entering names outside this
financial-source cohort are out of scope. This is a declared static initial
cohort adaptation,not whole-market coverage or a live constituent feed.

At each first actual2024/2025 exchange session,form at the immediately preceding
actual session's15:05Shanghai. Load the exact audited monthly source view in
RECONSTRUCTED_PUBLICATION_DAY_END mode. No later view may fill an earlier one.
Every394 source name gets an explicit retained eligibility/exclusion reason.
Require2021Q3 NONFINANCIAL_IN_SOURCE_VINTAGE,latest annual current source supported,
and positive finite formation close,volume and normalization factor.

The latest report must have fiscal year at least formation-year minus2 through
June30,or formation-year minus1 fromJuly1. This fixed18-month annual freshness
convention prevents indefinite carry of a missing annual report. It is an
experimental missing-data rule,not a claim about a statutory filing deadline
or a claim to reproduce the paper's June lag. Newly visible supported reports
may update the signal earlier; newer unsupported/identity-failed/ambiguous
reports block old-value fallback. No alternative missing-data run is selected
after observing performance.

Compute scores using exact rational arithmetic from the same visible current
report's three normalized CNY cells. Keep negative gross profits. No market
capitalization scaling,profit-margin substitution,industry score calibration,
winsorization or current-sector lookup. Rank descending with code-ascending ties.
Select floor(N/10) names,at least1,and equal-weight them to95% of equity. The low
control uses ascending ratios and the same tie rule; the broad control uses all
eligible names. Require at least100 eligible names and at least half the active
initial cohort at every formation; these are structural coverage/diversification
guards,not power-calibrated statistical thresholds. Their choice uses source
feasibility counts already observed,not investment returns.

## Execution,development and gates

Reuse the existing physically capped
`qlib-price-delay-pre2026-clock-v2-20261021` provider. Its quote values and actual
simulation calendar end2025December31. The next actual session appears only in
the exclusive-right-boundary clock file and has no quotes or simulated2026day.
Verify its complete inventory/manifest and all per-feature hashes before/after.
No copy or mutation of old providers is required. Hashing opaque original
source tails for provenance in earlier preparation is not decoding future
quotes or querying them as signals.

Use existing prior-close quantity planning and next-session daily-open Qlib
execution. Fix base buy5bp/sell15bp and minimumCNY5,with additional20bp and40bp
per side as two predeclared cost profiles.20bp is sensitivity only; selection
uses40bp. Open +/-9.5% proxy limits,normalized units,absent exact ST limits,
queue/volume/lot/tax/corporate-action mechanics and incomplete arrivals remain
engineering limitations. Daily reconcile must preserve equity/cash/orders/
holdings and prior-close sizing. No leverage or overnight short positions.

Use existing independent pre2026 gap-state captures to check missing held marks.
Unverified marks are counted and prevent lead admission; they cannot be waived
because returns look attractive. Any required additional source capture gets a
separate source-only request without modifying the financial ranking.

Only the fixed primary is a possible development lead. At40bp it must have
strictly positive net returns in both2024/2025,average exposure>=90%,zero
unverified held marks,and a complete reconciled continuous account. Report both
controls and their differences without claiming statistical significance or
LLM/RSI improvement. This is a feasibility gate,not proof of generalization.
On failure retain all outcomes and reject this registered trial; do not run2026
or tune this rule from2026. A positive screen does not bypass the business/
accounting/raw-share gate and does not itself authorize economic success.

## Files,freeze and verification

Add`src/stock_rsi/gross_profitability_monthly.py` for the signal/targets and
`scripts/run_qlib_profitability_pre2026.py` for the bounded six account runs.
Keep old source readers,requests,providers and failed strategies unchanged.
Behavior regressions first cover exact ratio/ties,all eligibility reasons,
freshness boundary,newer source failures,no cross-period view,current-source
identity,pre-close quote reads,coverage gate and no2026 boundary. Runner tests
exercise frozen contract/source mutation/fresh-only output/original error and
terminal preservation with a controlled external simulation boundary.

Freeze/push`experiments/qlib/gross-profitability-pre2026-request.json` before
real target formation or return calculation. Bind new code/tests/this plan,the
complete audited monthly availability source closure,its52 outputs and QA,the
physical quote provider inventory and existing independent gap-state files.
Request validation may read hashes/metadata,but not generate real ranks before
freeze. Run full unittest discovery using installed dependencies; no installs.

Run once in foreground,write each formation/target/account artifact without
overwrite/resume,preserve original exceptions and completed prefixes,and rehash
all inputs and the request even on failure. Failed persistence or changed input
prevents a successful summary. Separately audit actual target formation and
account arithmetic from immutable outputs before publishing a lead. Publish
derived counts/metrics and checks,retain originals/full raw outputs locally.
Push results and inspect hosted CI for the exact final commit.
