# Price-delay: preserve the failed source verdict and check account dependencies

The strict 2,502-sample minute admission failed: 2,490 ordinary samples
passed and 12 SZ002092 samples were rejected because the unchanged original
daily source has `isST=1`. Its complete capture is not execution admission.
The failure directory, original source bytes and original admission plan are
immutable. No 2026 candidate outcome has been queried.

The original target file selects SZ002092 only on 2024-01-02, using the
2023-12-29 close. The original daily source marks it ST on 241 sessions from
2024-05-21 through 2025-05-19. This identifies a conservative ever-seen source
prefix issue; it does not establish actual zero inventory or authorize
excluding any stock that is still needed by an account.

The separately versioned `ordinary_source_rows_on` guard uses the account's
current dependency set on every explicit session, before applying source
prices or executing orders. That set must include all owned and pending
shares, pending orders, required ex-date entitlements and the next target's
decision-price dependencies. If any required source is nonordinary, fail the
account without a forced sale, price substitution or alternate limit rule.
Unknown state and unexplained source gaps also fail.

An unused ST row can be withheld only with an evaluator audit recording its
actual absence from that account's required set on that session. Preserve
the raw row and state. These audit records must not enter decision snapshots.
Each of the six participation/cost accounts must establish this separately;
a previous daily proxy account or another participation profile is not proof.

`replay_ordinary_stock_distribution_targets.py` is a separate copy
of the original `replay_stock_distribution_targets.py` used by the frozen
price-delay daily account. It retains `plan_integer_targets`; it does not
switch to the budgeted allocator. Its function body and investment
allocator are unchanged; only the source-row guard import and explanatory
docstring differ. The original frozen replay and all historical evidence
remain unchanged.

This guard is preparatory code. It does not change the failed minute-source
verdict or authorize an account replay by itself. Before any new account
run, independently verify the failed verdict, freeze a distinct conditional
source scope admitting only the 2,490 ordinary packets, bind all 241 original
ST intervals and 12 rejected packets, and ensure the tape provider refuses
those rejected identities. Then freeze the six-profile account protocol.
Any remaining dependency on an ST row or unavailable tape must preserve a
failed account; do not retry with looser rules or tune investment targets.

The same frozen strategy must satisfy positive returns in each of 2024 and
2025 before its separately frozen 2026 diagnostic. The final objective remains
at least 10% for January–October 2026; an incomplete October observation cannot
prove that full-period objective. Neither this guard nor its synthetic tests
demonstrate investment returns, PIT completeness or real market execution.
