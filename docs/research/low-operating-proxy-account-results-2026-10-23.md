# Frozen low-OP account fails at a held delisting boundary

The continuous-account objective remains active and unachieved: 2024 > 0,
2025 > 0 and January–October 2026 >= 10%. No 2026 source values or outcomes
were used to select or repair this candidate. Previously exposed 2026 remains
exposed, and October is not complete as of October 23.

The frozen source/method/request commit was pushed and exact-remote verified
at `3dea700202bb6b979563805f16fd3995d4ba3eb7` before the first account run.
Request SHA256 is `d9024db0b0b37f00ccc0927fa8aea44f6d5bcfde37eecbb4f163d2db61fbdc55`.
Its GitHub Actions run 39961713099 passed all three jobs: Python 3.11, Python
3.12 and research dependencies. Notifications were not disabled.

Preflight authenticated 6958 bound inputs, 486 sessions, 43 instruments,
24 unchanged monthly targets, 64 cash-only events and one known applicable
financial correction. The corrected source score leaves every frozen target
unchanged. It does not establish cohort-wide amendment completeness.

## Native failure, not a completed return

The first extra-20-bps cost case failed at the primary delisting boundary for
SZ002505 on 2024-08-30. The last completed account day is 2024-08-29. Under
the frozen daily proxy the account bought 48,800 shares on May 6 at CNY1.07,
and 5,600 on June 3 at CNY0.96. Its 54,400-share sell orders eligible July 1
and August 1 both remained UNFILLED_MARKET_CONSTRAINT. Therefore the account
still owned 54,400 shares when the primary delisting guard fired.

The original failure and account prefix are retained. The 40-bps case did not
run. Neither annual ROI nor results.json was produced. The old normalized
Qlib development results do not replace this failed continuous-account replay.
No completed sale, later recovery price, zero write-off, fabricated market row
or ex-post removal from the frozen target universe was assumed.

Root checks authenticated 6959 inputs including the request, all four local
artifacts, and three public copies. The prefix has 158 fills and 160 orders.
Reconstructed cash CNY25,284.09 equals saved cash; integer share flows and
position lots match, and ex-date registered quantities match the saved
record-date receipts. This verifies the native prefix under shared accounting
conventions; it is not independent financial accounting assurance.

Root proof SHA256:
`363a65fef0ae99f58cf876e86fc4c13a0432ed71d63bc6d2ab6bf0d84412ada6`.
See the sibling experiment files `low-operating-proxy-account-terminal.json`,
`low-operating-proxy-account-failed-state.json`,
`low-operating-proxy-account-failure-audit.json` and
`low-operating-proxy-account-root-check.json`.

## Review, corrections and remaining costs

One fresh whole-change synthetic reviewer reported three Important findings
and no Critical findings. One correction pass, with no rereview, covered:
invalid annual results retained after publication failure; missing durable
failure terminals under input/output mutation; and monetary amendment payloads
parsed before the formation visibility gate. Added regressions first reproduced
these defects (two failures and three errors across subcases), then passed.
The corrected version passed 16 focused tests and 1532 full tests (23.757s).

The account-specific finalizer keeps the frozen source-only finalizer unchanged.
It clears canonical ROI fields and quarantines rejected result artifacts on
publication failure, retains native account stages and uses safe prior-failure
copying. Financial payload decoding and primary literal/PDF comparisons now run
only inside the identity/visibility-gated loader. The actual account failure
also demonstrates durable native-failure retention with unchanged inputs/outputs.

All review rulings and their costs remain explicit:

- Immutable prior methods required derivative replay/finalization code. Shared
  broker, accounting, hash and conservation helpers are not an independent audit.
- The single warning issuer/window, simulated permission and 500,000-share cap
  authorize only this conditional historical profile, not real investor access,
  other issuers, multiple correction chains or a general live executor. The
  replay calls one complete pending-order batch per session; repeated independent
  same-day helper calls have no general live cap-accounting guarantee.
- Historical joined names and positive volume infer the 43rd security's state.
  Annual-zero and no-observed-price-action evidence have conditional coverage.
  They do not prove native vendor flags, universal corporate completeness,
  actual auction depth, minute execution, FIFO taxes or historical arrival.
- Current amendment registration time is not historical receipt time. The
  reconstructed publication-end-of-day mode is disclosed. Malformed future
  base-record metadata remains fail-closed without invoking a monetary loader.
- Native processing retains valid corporate transitions completed before a
  later execution failure; transactional rollback of that prefix is not claimed.
- Source/PDF factual completeness, actual account performance, 2026, investment
  admission and remote/CI completion were outside the synthetic review. Source
  evidence and remote/CI were checked separately; performance remains incomplete.
- The PENDING review placeholder was replaced by the actual review record before
  freeze. There are no deferred Minor findings.

The user's all-lawful-fractional-branches rule remains in force. This event set
contains zero stock/capital distributions, so it needs zero such allocation
branches; it does not retrospectively resolve prior fractional-share failures.

## Next research boundary

This frozen candidate does not pass account feasibility. Preserve it as a failed
experiment. Any continuation must separately freeze its data/event/risk model
before outcomes, retaining the unavailable delisted-share claim rather than
inventing liquidity. A new policy must have its economic hypothesis and general
eligibility/exit rules defined from development data; removing SZ002505 after
seeing this failure is not validation of the original strategy. No 2026-based
parameter or stock selection is permitted. No broker orders were placed.
