# Separate registry uncertainty paths for the unchanged strategy

User choice: retain the strict registry-allocation failure and enumerate a
conservative allocation envelope. This changes the explicitly stated account
model for an additional diagnostic, not the investment strategy, source event,
original account or previous failed result. It cannot certify an actual CSDC
allocation or make an incomplete October complete.

## Source and local integer envelope

Use the original SZ002831 notice SHA
`ae29cedfb8dd555a2c0f624a05fe0d91484b67d29fc5ba1118dfca79a52f5922`,
recordJune3/exJune4,367817529 declared capital shares,915182294 eligible original
shares, and4.019063 displayed capital shares per10. The original scalar
0.4019063 remains unchanged. Whole-register remainder ordering and random ties
cannot be inferred from one account's lots.

`registry_allocation_bounds.allocation_bounds` consumes a separately bound
event/component proof and the entire actual registered quantity. As an explicit
engineering assumption, the last displayed per10 digit defines a symmetric
precision interval, divided by10; the exact total/eligible ratio must lie
inside it. This is not a certified issuer rounding algorithm. Return every
integer from floor(q*lower) to ceil(q*upper), including both endpoints. Reject
more than three local candidates or any candidate above the declared total;
never clip or pick one. Forq900 this yields361/362. Exact-ratio integers alone
do not collapse the display uncertainty interval. Zero holdings produce zero.
Candidates need not all be feasible in the unknown joint register and have no
certified probabilities. Floored shares need not minimize final portfolio ROI.

## Separate account adapter

`RegistryAllocationAccount` preserves the old stock account's clocks, payment
timing, tax guards, T+1, cash and corporate ledgers. Integer entitlements behave
exactly as before. For a noninteger component, require a proof matching the
immutable event identity, issuer, component, published/record/ex dates and
original scalar; call the pure local-envelope helper as of ex-date09:30.
No proof retains the old refusal. A missing choice raises a structured
`AllocationChoiceRequired` before any due cash payment, share credit, clock or
allocation-audit mutation. A choice must be an actual integer in the complete
candidate list. The source scalar, event ID, record ownership and tax evidence
are never changed. A standalone allocation audit records model choices and
provenance without entering investment snapshots or implying actual allocation.

## Complete tree, then returns

Freeze the additional proof, account, reconciliation, driver and request before
reading a new full-horizon portfolio result. Reuse all original source/event/
target bytes, SSE epochs, unsigned ST capability, integer allocator and both
20/40bp costs. For each cost, start with no choices and replay from the same
2023 anchor. At a structured choice point, preserve the partial node and create
every child in canonical candidate order. Each child starts the continuous
replay again with its explicit choice map; no state or performance-based
pruning, probability weighting, target change or annual reset is permitted.

The resource cap is128 attempted nodes per cost, fixed before results. Exceeding
it, an unsupported proof/state/tax condition, failed conservation, partial leaf
or source postcheck failure prohibits aggregate ROI approval. Never drop a bad
leaf. All complete leaves must preserve the original584day/30intent strict
prefix and the old541/27 and486/24 financial evidence. Independently reconstruct
cash, T+1 lots, fees, selected integer entitlements, pending stock, claims,
marks, ownership and equity; verify each fractional component has exactly one
matching audit entry and no orphan choice.

Only after all nodes terminate in admitted branches or complete leaves, every
leaf passes conservation and all source postchecks pass may annual returns be
computed. Publish every leaf and min/max across the complete admitted model
envelope, for each cost. Report whether all leaves meet2024>0,2025>0 and the
fixed interim2026>=10% condition. A favorable leaf is insufficient. The2026
denominator remains actual2025 year-end equity in the same account.

This is an explicitly assumed daily engineering envelope, not verified actual
registry execution, complete PIT/arrival, queue/impact, true FIFO taxation, a
sealed2026 holdout or the unfinished full-October objective. Keep all those
limitations and both strict failures visible even if the interim numeric
conditions eventually pass.
