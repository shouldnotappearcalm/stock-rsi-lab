# Frozen low asset expansion fails the2026 return requirement

The frozen conditional low-asset-expansion strategy does **not** meet the
required three-period return criterion. The same continuous account earns
positive2024 and2025 returns, then loses money in2026 throughOctober21.
Do not promote it, alter it from2026 failure patterns, or report its earlier
profits as meeting the current objective.

| Extra execution cost | 2024 | 2025 | 2026 Jan–Oct21 | 2026 max drawdown | 2026 average exposure |
|---|---:|---:|---:|---:|---:|
|20bps|+17.13673%|+14.98989%|−17.32086%|−25.60045%|94.27868%|
|40bps|+16.27102%|+14.48632%|−17.91295%|−26.00633%|94.30756%|

Each case starts with CNY1m in the same continuous account; no yearly resets.
The2026 denominator is respectively CNY1,346,953.9500 and1,331,144.1500 on
December31,2025. Ending equity is CNY1,113,649.9500 /1,092,696.9000. Both cases
contain191 actual2026 sessions and34 monthly decisions over the full horizon.
These losses occur with high exposure under the unchanged95% target allocation.

## Frozen run and source repair

Freeze commit `539dfa92a5ae3443d01d73aa4edaa908e75ed210` was pushed and remote
identity verified before preflight and the single actual replay. Request SHA256
`12a0394d146922707a99edecb739b5482c068e939b535f9a9a19e2974f4c3377` binds1123
inputs, plus the request itself. Both cost cases completed without original,
persistence or posthash errors. All1124 consumed inputs remain unchanged.
Full artifacts reside locally in `asset-expansion-tax-proven-account-20261023`.
Public production summary: `experiments/qlib/asset-expansion-2026-tax-proven-account-results.json`.

Only the independently authenticated SH603737 June1,2026 capital-tax proof was
added. All141 event economics/timing and all original79 event identities remain
unchanged; only the specified event's proof, verified flag and identity change.
The 2700 registered shares credit exactly540 capital shares once in each case.
The other3 unverified noncash events have zero actual registered inventory.
The original strict failures and source-parser rejection remain preserved.

The source repair does not modify strategy,34 frozen targets,95% desired
allocation, monthly prior-session15:05 decisions, next-session09:30 daily-open
proxy, integer sizing, base5buy/15sellbps/minCNY5, extra20/40bps profiles or
flat20% cash-dividend stress reserve. An issuer's explicit tax statement is
not statutory tax certification or actualFIFO settlement.

## Independent validation

The separate checker imports no production account, broker, compiler or signal
code. It reuses the pinned independent ledger algorithms with explicit AST
adaptations: policy labels,24→34 decisions,179→141 events,485→676 account
sessions,486→677 source sessions, one lifecycle loop guard, one final-state return and an explicit
May29 checkpoint capture/initialization/return. It reconstructs the actual raw source141events and receipts, reads the
original4page tax notice with both PDF parsers, and authenticates all100 raw
reconstruction outputs against the prior separate source QA.

For each case it reconstructs every order/status/fill, affordability and fees,
integer lots/T+1, record/ex entitlements, cash availability,540share credit,
claims/reserves, daily equity, all34 decision snapshots and the exact2026 annual
denominator. Results:441/440 orders,426 fills each,318 corporate-ledger entries
each, zero whole-day volume violations. No unpaid cash or pending stock claim
remains at the cutoff. Opening liquidity and price impact remain unverified.

All original486 daily rows including initialization, ownership records,
24 intents/snapshot hashes, full December31 order/fill checkpoint and79event
ledger prefixes agree. The42 additional old dependency ledger entries are
zero. The new account also passes the entire prior stopped-account checkpoint
beforeJune1 with only the explicit authenticated event-ID substitution.
All136 post-exit sessions require no actual SH603056 inventory or claims;
no stale mark, synthetic sale or recovery amount is introduced.

Eight arithmetic controls fail without relying on an artifact hash gate:
erased fee, forged daily equity, false registered quantity, forged snapshot,
missing540share credit, a false post-exit claim, false prior-partial cash and
false prior-partial owned shares. The first checker returned a pass, but final
review found it trusted the production partial-state flag rather than parsing
the old interrupted states. Its code and receipt remain retained as v1/incomplete.
The separately versioned v2 reconstructs May29 from the independent daily ledger
and compares all10 state fields to each old interrupted account, allowing only
the authenticated event-ID map. Both checks pass:375 fills and401 orders each.
The Important finding was reproduced by failing tests, then corrected; no actual
account or investment method was rerun. There were two actual QA executions. All20 actual output files remained
unchanged through QA.
Public receipt: `experiments/qlib/asset-expansion-2026-tax-proven-ledger-audit.json`,
SHA256 `8f955eba5093d84a80e8737e02baf2d5cfc201310bca06227a76fefa218156d1`.

This remains daily-price engineering/research evidence. Historical source
arrival is reconstructed,2026 was already exposed, fullOctober is unfinished,
and actualauction liquidity/FIFO settlement are unverified. The investment
objective is still open. Reject this candidate and begin any further method
search from pre2026 information and independently motivated hypotheses; retain
all trials and do not use2026 failure anatomy to choose rules or parameters.
