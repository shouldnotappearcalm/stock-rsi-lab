# Raw-overlap schema continuation: preserve the after-tax source literal

The first frozen check completed all 47 names with 262 unchanged inputs and
no calendar error, but blocked 40 names: 190 packet alternatives contain a
nondecimal `dividCashPsAfterTax` string. The source can enumerate alternatives
using the literal `或`. That optional descriptive field was incorrectly treated
as one numeric quantity. The original check/output/request remain immutable;
the prepublication v1 draft was never executed. No account return was computed.

Create `scripts/inventory_asset_expansion_raw_horizon_v2.py` as a bounded copy
of the first checker. Remove **only** `dividCashPsAfterTax` from the fields
subject to numeric interpretation. Preserve its complete string in original
packets, canonical row identities and overlap comparisons. A changed literal
still blocks the affected route; never select a tax value, discard the field,
rewrite raw records or infer the account tax treatment from it. This gate
makes no claim that an agreeing after-tax literal is an account entitlement.
The already-frozen account uses gross cash and a flat 20% stress reserve.

The only other changes are module description, versioned plan/request/output
identities, v1-result evidence binding and the method/test dependency list.
A contract test must verify those exact textual differences, leaving every
other source rule, validation, session/issuer/date guard, all-alternative
comparison, route order, quarantine stop and persistence mechanism unchanged.
Run the original 13 synthetic contracts against both checker versions; add
checks that multiple after-tax alternatives remain literal, a literal change
is a conflict, and none of the gross/stock/factor numeric checks are relaxed.
Run the full suite, freeze/push v2 method/request/test/plan and all 254 original
source hashes before the next real source check. Use a new output directory,
no overwrite/resume/network/account/strategy invocation. Preserve both outcomes.

This continuation addresses a source-schema bug, without changing any
investment rule, target, cost, tax reserve, account denominator or source
issuer scope. All 47 names and all 13 cache alternatives remain required.
Any remaining schema/content/quarantine/calendar conflict blocks reuse.
Complete source-extension and account admission remain separate stages.
