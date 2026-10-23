# Frozen 47-name raw-source overlap check before extension

Continue the target-stage plan. This gate reads original raw packets only to
check source identities, schemas, complete explicit calendars and overlapping
history. It never runs a policy, values a portfolio or changes a target.
The fixed cutoff remains October 21, 2026, at 15:05 Asia/Shanghai. Existing
cache windows stop earlier; neither cached metadata nor this gate establishes
complete raw coverage through the cutoff or actual historical arrival.

## Implementation and verification

- Add `scripts/inventory_asset_expansion_raw_horizon.py`, using only the
  standard library. Authenticate an externally supplied frozen request SHA,
  the prior metadata-only inventory, target/summary/separate audit, original
  cache manifests, calendars and every matching packet before decoding bars.
  The request binds methods, tests and this plan. Push it before execution.
- `validate_packet(packet, code, sessions, window)` requires canonical dates,
  exact unadjusted BAR/DIVIDEND/ADJUST schemas, finite nonnegative market and
  distribution amounts, positive trading OHLC/preclose/volume and adjustment
  factors, canonical numeric event identities, unique ordered operation dates
  on explicit sessions, issuer/adjustment/status identity, and one
  bar for every explicit session. No rows or sessions are synthesized.
- `compare_packets(left, right)` compares all overlapping bars and accepted
  distributions/adjustments by operation date, preserving string identities
  and using exact Decimal equivalence only for numeric columns. Retain every
  field/date conflict and both row digests. Quarantine records with missing
  dates remain unresolved; they cannot be silently dropped for reuse.
- `audit_inventory(inventory, base)` checks every original alternative for
  every one of the 47 historical dependencies, not just 22 names selected in
  2026. Calendars must agree on their entire overlap. A schema/calendar or
  content conflict blocks reuse for the affected name; a calendar conflict
  blocks all routing. Otherwise choose the longest complete prefix, with
  lexical cache name as the fixed tie order. No return or data convenience
  may remove a dependency. An unresolved quarantine blocks that name.
- The CLI persists a fresh output directory, request, completed per-name
  records, input-before/after hashes, pending names and original exceptions.
  No overwrite/resume or network call. Record all inputs unchanged before
  calling the local check complete. Completion is not account admission.
- Add synthetic tests in `tests/test_asset_expansion_raw_horizon_inventory.py`
  for equal prefixes/numeric formatting, market-state and corporate conflicts,
  schema/NaN/future/date failures, missing sessions, quarantine, conflicting
  calendars, complete dependency retention, changed inputs and interrupted
  persistence. Observe test failure before implementation, then run the full
  unittest suite. Freeze/push before inspecting real 2026 raw packet values.

## Subsequent stages

Publish the complete overlap outcome including failures. Freeze a separate
fixed BaoStock source-extension protocol only after resolving source conflicts;
retain every original failed capture. Acquire explicit calendar and missing
raw daily/action tails through October 21, with bounded queries/attempts,
then authenticate reconstructed sources independently. Neither this gate nor
a later extension may change the 100-name floor, 95% weights, original policy,
continuous CNY 1m capital, 20/40bp extra costs or 2025 year-end denominator.
Any fractional registry uncertainty retains strict failure plus all lawful
branches under the user's existing approval. Portfolio/account returns and
separate ledger audit follow source admission; all three return requirements
remain open, and previously exposed 2026 is not sealed.
