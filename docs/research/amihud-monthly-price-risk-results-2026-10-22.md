# Fixed monthly risk overlay: complete pre2026 result

The frozen `amihud22_monthly_price_risk1` candidate fails the required development
criterion. All three reference accounts lose money in2024, despite positive2025
returns and average exposure above92%. No2026 diagnostic was opened.

| Participation, extra cost40bp, capitalCNY1million | 2024 net return | 2025 net return | Mean exposure |
| --- | ---: | ---: | ---: |
| 100bp | -1.538984% | +8.849774% | 92.293346% |
| 500bp | -1.520039% | +8.943238% | 92.303384% |
| 1000bp | -1.520039% | +8.943514% | 92.303322% |

Returns use physical shares, actual source prices under the frozen conditional
minute scenarios, fees, corporate flows and the same continuous account. The
2025 denominator is2024 year-end wealth; accounts do not reset annually.

## What the risk module changed

All24 monthly decisions were independently reconstructed from912 prior-visible
four-cell observations. Only the2024May31 formation changed: raw close below
CNY1 excluded one original selection and redistributed its target budget. In
all three reference accounts, the resultingJune3 sell instruction actually
filled21900 shares ofSZ002505. Original desired weights are not substituted for
actual holdings. The prior Amihud seed and all its60 failed account artifacts
remain byte-identical.

Of60 new complete scenario attempts,55 finished the full486-session account
including warmup and all24 monthly intentions. Five scenarios, all atCNY100million
capital and100bp participation, still fail at the2024August30 delisting boundary:
each actually holds108200 shares ofSZ002505. These failures have162 completed
sessions and8 intents, with last completed clock2024August29 phase1. No partial
annual return is assigned. Smaller-capital executable exit does not establish
an executable exit at larger size.

The module improved the observed exit behavior. Its investment results still
fail2024>0,2025>0. This is one adaptive pre2026 experiment, not evidence of a
published complete method, RSI superiority or a new sealed holdout. Do not tune
the threshold, costs, dates or stock selection from these outcomes to relabel
this candidate, or open2026 to rescue it.

## Freeze and independent verification

Source-only methods/request were pushed at`34f32c4` before real target generation.
Their request SHA is
`877fa81f5b081f97f6dc55798e3d87709a2da4a64e62225e747471f66787c5d6`.
Independent source-only reconstruction was frozen at`8f997d8`. Root and reviewer
produced byte-identical source-audit report`51cb2a1a…f952428`: all24 targets and
receipts,912 accesses, exact weights, unchanged2276 active/18 nonexecuting minute
intervals,2905 inputs,8 outputs and9 rejected negative controls.

Account methods, complete60-profile matrix and separate ledger auditor were
frozen and pushed at`020c132` before actual accounts. That commit's three CI jobs
passed. Account plan SHA is
`06ff6d821f827a632aba81ac5637180b0274947625a00106ea6b68921f53441b`.
Preflight and actual run exited0; all2919 bound inputs passed final rehash,
including all307 actual old failed-account artifacts. New run has527 output
files:55 times9 complete-ledger files,5 times5 failure files and7 root records.

The separately implemented stdlib auditor imports no production account,
simulator, scorer or data modules. Its first actual run exited0, reconstructed
all55 full accounts and all5 strict terminal failures, including cash, FIFO/T1
inventory, integer child orders, fills, fees, corporate entitlements, claims,
marks, daily equity, source-window capacity and decision-evidence IDs. Only after
all60 reconciled did it independently recompute continuous annual returns and
the original three-reference gate. Seven actual/source mutation controls were
rejected; its separate synthetic selftest includes16 negative controls.
The reviewer separately reran the frozen auditor and obtained byte-identical
output. The report SHA is
`16963e94156174abaa4455d2f0ba536034f0b673bad3da53e20f48a0dbebf8fd`.

Source admission stays false. Archived cent-grid/binary32 and clock scenarios
remain conditional; historical data arrival, statutory FIFO tax, actual queues,
market impact and certified liquidity remain unverified. Source-only risk
eligibility is not a statutory20-day delisting detector. October2026 is
incomplete, and the original three-period investment objective remains open.

Evidence:

- [Plan](amihud-monthly-price-risk-plan-2026-10-22.md)
- [Frozen account plan](../../experiments/qlib/amihud-monthly-price-risk-development-plan.json)
- [All60 outcomes](../../experiments/qlib/amihud-monthly-price-risk-development-results.json)
- [Independent ledger reconstruction](../../experiments/qlib/amihud-monthly-price-risk-development-independent-ledger-audit.json)
- [Execution and profitability diagnostic](../../experiments/qlib/amihud-monthly-price-risk-development-diagnostic.json)
- [Run verification and527 hashes](../../experiments/qlib/amihud-monthly-price-risk-development-run-verification.json)
- [Independent target reconstruction](../../experiments/qlib/amihud-monthly-price-risk-independent-target-audit.json)
