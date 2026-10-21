# Mixed-distribution source precision, before any 2026 account outcome

Problem: the independently reviewed SZ002831 June4 implementation notice states
cash8.038127CNY and capital4.019063shares per10 eligible original shares.
Vendor scalar fields retain only0.803813 and0.401906 per original share. The
existing cash-only truncation-completion contract correctly rejects this mixed
event and downward cash correction. Neither vendor rows nor that old contract
may be rewritten. A precision capability cannot resolve shareholder-register
allocation or strengthen tax evidence.

Add a separate evaluator-only module
`src/stock_rsi/distribution_event_compiler_v3.py`. Leave v1/v2 and every account,
investment rule, target list and old source/financial artifact unchanged.

The new `PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION_V1` contract accepts explicit
event-keyed corrections only for a vendor-backed positive-cash, positive-capital,
zero-stock event with a listed date. Require exactly the cash and capital
components, the original full row digest, matching document issuer/announcement/
PDF hash, original record/ex/pay/list dates, positive source-page references,
exact primary per10 units and effective per-share values. Each vendor scalar
must have six published decimal places. The exact primary value divided by10
must equal the proposed effective per-share value and lie within the vendor
scalar's half-last-decimal interval. Both increase and decrease are allowed;
this proves display-precision consistency, not the vendor's rounding algorithm.
No prices or adjustment factors are inputs.

`apply_component_precision` operates on paired already compiled events/receipts,
checks their original vendor economics and identities, rejects duplicate/orphan
proofs, creates a new event identity containing the old ID and complete precision
proof hash, and records old/effective component values plus primary provenance.
For each corrected key, independently call the unchanged v2 compiler on that one
original row and its corresponding original tax proofs, with no supplements.
Require complete event/receipt equality before correction; caller-paired IDs or
tax flags alone are insufficient. This does not compile unrelated pre2026 rows.
It must preserve dates, original row hash, all tax flags and taxable-stock bases.
`compile_distribution_events_v3` delegates all original compilation to v2 then
applies only the separate mixed-component contract. No corrections must return
the exact old events and receipts. Existing cash-only precision remains separate;
an event cannot receive both contracts.

The later append-only caller may use the unchanged old `compile_append_only`
then apply this adapter to the combined results, requiring all original378
event/receipt objects and original files remain identical. Actual source use
is not authorized by this design alone: freeze the proof projection/compilation
request with complete primary evidence and exact current key whitelist first.

Behavior checks precede implementation: original outputs unchanged; mixed
cash decrease/capital increase from exact per10 units; immutable inputs and
deterministic new IDs; document/row/date/page/units tampering rejected; unsupported
components, nonfinite/zero/negative amounts, six-decimal interval violations,
duplicate/orphan proofs and dual-contract events rejected. Assert no tax upgrade
and that the unchanged account still rejects noninteger entitlements before
cash/share mutation. Full tests and independent code review precede any actual
event compilation.

The current notice describes remainder ordering and random tie resolution using
the full register. That register is unavailable. Keep the strict account guard;
do not invent rounding, allocation, zero ownership or cash-in-lieu. SH603606 and
SZ000937 unresolved tax markers remain explicit, and SH603596's new2026 proof
does not change its old2024 guard. This is source/evaluator engineering, not a
new investment strategy or a result-driven parameter change. No2026 portfolio
return has been calculated; full October is incomplete and the objective remains
unachieved.
