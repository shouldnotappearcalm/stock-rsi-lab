# One adaptive monthly risk-module trial

This is a new development candidate, `amihud22_monthly_price_risk1`. The original
Amihud22 strategy, 60 failed accounts, delisting failure, source admission,
account, broker and evaluator stay byte-identical. It is an adaptive experiment
informed by a 2024 failure, not a previously published complete trading method.
Prior 2026 outcomes have already been exposed in this project; this trial does
not acquire sealed-test status.

## Investment change and causal inputs

Keep the original 22-session Amihud ranking, original historical universe,
original selected names, 24 month-end formation times and monthly execution
schedule. At each immediate previous explicit exchange close, read only the
selected name's `date`, unadjusted `close`, `tradestatus`, and `isST`. Exclude
known halted or ST names and active names with raw close below CNY1.00. Unknown
flags, missing cells, nonpositive/non-cent active prices fail generation.
There is one threshold and one candidate, with no price-threshold search.

If none is excluded, preserve original JSON weights exactly. Otherwise keep
remaining names' relative weights, redistribute the original 95% target budget,
round all but the last sorted name downward at 24 decimal places, and give the
last name the exact residual. All excluded means explicit zero weights on the
original names. Desired zero inventory does not establish an actual exit:
unchanged account, halt, ST, corporate and lifecycle guards can still fail.
The wrapper never silently marks such a failed account flat or profitable.

The threshold is a heuristic inspired by the SZSE August2023 listing rules
(effective September4,2023) and SSE December2020 FAQ. It is not the statutory
20-consecutive-trading-day classifier or the 10-day warning rule. The January9,
2024 SSE case only corroborates a pre-existing rule; it is not an input to the
January2 decision. Monthly observation may miss risk arising between formations.
The primary source review does not certify rules throughout 2024–2025 or prove
an investment advantage. A 2026 trading-rule search snippet was incidentally
visible during research, was not followed, and did not set this rule.

## Source-only freeze precedes real target generation

`src/stock_rsi/monthly_price_risk.py` contains the pure transformation.
`scripts/build_monthly_price_risk_targets.py` authenticates the original source
plan, all original data/methods, the complete 22-file primary evidence set and
all 307 actual old failed-account files. Primary scope and hashes must match
the independent review and public discovery record; a reduced or empty map
cannot pass. Old failure hashes must match both independent audit and public
verification, with exactly 60 profiles times five files plus seven root files.

Freeze `experiments/qlib/amihud-monthly-price-risk-target-request.json`, including
all input and method SHA256 values, before producing real targets. Push the
freeze and verify CI. The request permits only 2023December29 warmup and
2024–2025 formation, no account/ROI calculation, no 2026 evaluation or network.
The builder rejects an existing output directory and always rechecks inputs and
request after processing, retaining the original exception and terminal record.
Output is eight files under local `amihud-monthly-price-risk-targets-20261022`:
targets, formation receipts, formation accesses, minute requirements, input-before,
input-postcheck, terminal, summary. Recompute all 24 targets independently before
any account run. New required execution sources must be a subset of the unchanged
2276 active and 18 nonexecuting source intervals. Subset coverage is not source
admission or verified historical arrival.

## Physical account confirmation is separately frozen

After source-only generation and independent verification, separately freeze a
wrapper and account plan. Reuse the original `run_profiles` and all its account,
broker, lifecycle, corporate and cost logic; replace only authenticated desired
targets. Keep all 60 profiles: participation100/500/1000bps, extra cost0/5/10/20/40bps,
capital0.1/1/10/100million CNY. Continuous account2024January2–2025December31,
not annual resets. The existing inner decision seed ID `amihud22` continues to
identify the base alpha; outer strategy ID and each target's `risk_overlay`
identify the new composite. No monkeypatch or old-file edits.

Keep original referencecapital1million, all three participation profiles at40bps,
both years strictly positive and original confirmation requirements. Do not
select a fortunate capital, cost or partial-year path. Reconstruct all daily
account states, fills, corporate entitlements and failed terminal states with a
separate stdlib auditor. A fractional-share guard remains a strict failure;
any legal allocation envelope requires its own bound source and complete branch
replay while preserving that strict failure. User authorized this envelope
approach; the earlier price-delay361/362 experiment already tested both leaves
and failed its 2026 criterion. It must not be rerun or relabelled as a new success.

Only a candidate passing pre2026 confirmation can get a separately frozen2026
diagnostic. Required goal remains2024>0,2025>0,2026January–October>=10%; October
is incomplete on2026October22. No result is promised. Both the archived minute
source scenario and future account result remain conditional engineering:
historical arrival, official cent-grid promotion, FIFO tax, queue and impact
are unverified. Source-only target generation proves no returns.

## Validation and exit criteria

Behavior tests cover exact1CNY boundary, missing/unknown rejection, no-op
preservation, exact95% proportional budget, all-cash sell intents, name-agnostic
eligibility, prior-close-only requests, future perturbation, authenticated
complete22/307 artifact scope, byte tampering, frozen request permissions,
existing-output protection and interrupted generation retaining original errors.
Run `PYTHONPATH=src python -m unittest discover -s tests -v`. Review and push before
real generation; independently reconstruct targets; freeze and review the wrapper
before accounts. Record failure without adjusting threshold, dates or gate.
