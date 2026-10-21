# Price-delay: six frozen pre-2026 minute-execution accounts

Run one unchanged `price_delay_d1` candidate with the original 24 monthly
targets, 151 original raw histories, 378 compiled company-action events and
CNY 1,000,000 continuous account from 2023-12-29 to 2025-12-31. Annual returns
use initial capital for 2024 and the same account's 2024-12-31 equity for 2025;
no annual reset. Decision time remains prior close 15:05 Shanghai time.

Preserve `plan_integer_targets`, the exact allocator used by the frozen daily
account. The separate guarded replay function has the same AST as that
original replay, with only its source-row guard import changed. Do not switch
to the budgeted allocator, change factor direction, weights, target dates,
holding rules, account capital, tax evidence or source data.

Execute all six combinations: participation 100/500/1000 bp and extra cost
20/40 bp. Retain original buy 5/sell 15 bp plus minimum CNY 5 per actual fill,
with the fixed extra cost added separately. The reference is 100 bp
participation and 40 bp extra cost, chosen before outcomes. Treat other
profiles as execution sensitivity, never a means to pick a winning result.

Use the unchanged nested broker: each child is sized using the immediately
previous completed five-minute sampled volume bucket, then priced against
the following bucket's adverse sampled price with a conservative volume
lower bound. Preserve explicit exchange sessions and lunch, legal trading
windows, integer and 100-share buys, T+1 sellability, protective price guards,
cash conservation, expiry and corporate-action ownership/payment rules.
The account cannot use a window's sale proceeds to size its simultaneous
buys. No official queue/impact realism is claimed.

Authenticate the independently reconstructed ordinary source scope before
any account. Its 2,490 executable packet hashes must exclude all 12 retained
ST rejection identities. The original 2,502-sample strict admission stays
failed. On each actual account session, the ordinary source guard must fail
before mutation if a ST row is required by owned or pending shares, orders,
positive ex-date entitlements or the next decision's prices. Save all 241
actual unused-ST audit records as `source_scope_audit.json` per profile;
require exact agreement with the source interval inventory. Do not infer
those records from monthly targets or a different account.

Require exactly one zero record-date ownership entry for the unsupported
SH603596 2024-05-20 noncash-tax event, independently in every profile.
Owned noncash entitlements require the original reviewed evidence; the
SZ002155 conditional tax inference remains conditional. Never promote the
unproved tax flag or create missing source prices. Preserve source packet,
primary-document and event-compilation hashes.

Save all six results and partial failure states, including pending parent
instructions, children/fills, owned shares, entitlements, cash/stock claims
and last clocks. Do not rerun an existing directory, silently retry a failed
case, widen the source scope or choose a different allocator after a result.
Missing required tape or ST dependency is an account failure.

Development confirmation requires all three 40 bp profiles: complete 485
2024–2025 account sessions plus the initial anchor, 24 monthly decisions,
positive returns in both 2024 and 2025, at least 90% mean exposure, all 241
unused-ST records, supported actual noncash ownership, legal child sizes and
no whole-day capacity violations. Independent ledger reconstruction must
precede any 2026 diagnostic. Preserve every 20 bp sensitivity result too.

This phase reads no 2026 quotes or outcomes. Historical arrival, PIT universe
completeness, original minute date echo, exact volume precision, actual FIFO
tax, official queues and calibrated impact remain unverified. Passing this
phase does not prove investment validity or the user's January–October 2026
>=10% objective. Any subsequent 2026 run needs a separate frozen protocol,
the same continuous account prefix and the same investment method.
