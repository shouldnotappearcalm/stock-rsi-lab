# Frozen price-delay horizon raw source capture

This is a source-only extension of the already frozen `price_delay_d1` rule.
The investment objective remains a single continuous account with positive
2024 and 2025 returns and at least 10% in January–October 2026. This capture
cannot establish that objective: its last available session is 2026-10-20,
full October is incomplete, and no portfolio return is computed here.

## Frozen scope before network access

- Keep all 34 monthly targets unchanged, including all original 24 development
  targets and their regression receipts. The target SHA-256 is
  `5d122dac55da8f57934524de0b6e3640a303363aca49e0a0a09dd70d5850a923`.
- Capture exactly the union of 203 target names over the explicit 676 sessions
  from 2023-12-29 through 2026-10-20. Never synthesize a session or bar.
- Preserve the original 151 raw source packets, their literal 486-session
  pre-2026 prefix, and all 48 development financial artifacts byte-for-byte.
- Fixed cache priority: `szse-value-momentum-raw-full-v2-20261021`,
  `low-beta60-raw-horizon-20261021`, `reversal-raw-full-20261017`,
  `szse-value-raw-full-20261017`. No selection by an account outcome.
- Reuse source observations for 102 whole-cache names. This is authenticated
  assembly with retained lineage, not a byte-copy claim for the new packets.
  The remaining 101 names comprise 80 incremental and 21 cold names.
  Sixteen new partial-cache names obtain complete old-window baselines from
  their registered cache; the original 151 baselines stay unchanged.
- Incremental names require exactly three logical queries: daily unadjusted
  bars, 2026 operate-year distributions, and adjustment rows, each from
  2026-01-01 through the cutoff where applicable. Cold names require five:
  full-window daily bars and adjustments plus operate-year distributions for
  2024, 2025 and 2026. Total maximum reservations: `80*3+21*5 = 345`.

## Bounded foreground collection and retained failures

Use installed BaoStock 0.9.4 with a 20-second socket default timeout, restored
on exit. This bounds the socket setting, not a guarantee of total request
duration or a certification of internal SDK transport attempts. There is one
administrative login attempt and one application attempt per logical query.
Stop after three consecutive failed securities. No automatic retry, restart,
resume or parallel capture. Preserve responses, reservations, errors, pending
names, partial output, logout result and abnormal exit. Existing output fails
closed before connecting. A subsequent attempt requires a separate documented
request and output identity; do not erase the failed run.

The unchanged source helper saves the decoded vendor response before validating
or projecting it. Future or undated distribution rows are quarantined. A
partial response, missing session, schema change, unexplained source conflict,
failed login/logout, changed source input or incomplete 345-reservation run
cannot be reported as complete.

## Previously authenticated coordinate references

The only permitted cross-cache coordinate differences are the four registered
issuer/root pairs for SZ002608 and SZ002756 against the reversal and SZSE-value
raw caches. Their raw daily fields, distributions, pre-2026 adjustment rows,
and all common non-fore-adjustment fields agree. Each exact previously saved
Fraction proof is bound in the request and reproduced against its saved source
bytes. Independent audit authenticates the original two notice PDF bytes and
their complete HTTP receipts plus the six underlying SDK query receipts.

Reuse these proofs unchanged as lineage. Do not rewrite source adjustment
coordinates, infer cash/tax from factors, create new cash entitlements or infer
the economic cause of a factor change. The two older coordinate references are
excluded only from the strict same-coordinate equality list; they remain
registered and hashed. Every other overlap stays strict. Any difference outside
these exact four pre-existing proof identities fails before network access.

## Freeze, run and exit criteria

`experiments/qlib/price-delay-horizon-raw-source-request.json` binds exact code,
protocol, inventory, independent source/formation/coordinate evidence, source
manifests/calendars, all original packets, target identity, source routes,
financial artifacts, fresh/baseline lists and four coordinate proof hashes.
An external request SHA is mandatory. Run `--preflight-only`, behavioral tests,
the full repository suite and code review; commit and push before the first
new source query. Preflight creates no output directory or SDK client.

Run `scripts.capture_price_delay_horizon_raw` once in the foreground with that
request and external SHA. Postcheck the same frozen inputs. Keep the legacy
helper manifest unchanged; write a separate price-delay scope record binding
the request, manifest, cleanup, postcheck and reused coordinate proofs.
Completion requires the exact 203-name set, no errors or pending names, all
345 reservations, successful login/logout and unchanged frozen inputs.

Collection completion does not admit these sources into the account simulator.
Independently authenticate receipts and source assembly, resolve corporate
action evidence and ordinary-share execution scope, then freeze account replay
instructions before computing the 2026 continuous-account result. Historical
arrival, full corporate action coverage, actual tax liability and real market
fills remain separate evidence boundaries. Never use 2026 returns to change
this rule, its parameters or target lists.
