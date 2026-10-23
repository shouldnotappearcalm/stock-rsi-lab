# Local pre2026 quote reconstruction hypothesis

Previous turn made progress:8f37dc2closed33issuer tax-text parsing failures and
published42risk views/63receipts/126unselected options plus both failed HTTP
attempts.1450tests/threeCIjobs passed. The full2024>0,2025>0,2026Jan–Oct>=10%
objective remains active/unachieved. Standing native implementation/test/public
push authorization applies in the existing pead worktree.

## Source hypothesis and limits

Freeze one local source hypothesis before reading new quote values: normalized
OHLC/factor recovers raw OHLC; normalized volume*factor recovers upstream volume
units. Official Qlib YahooNormalize1d adjusted_price/_manual_adj_data supports
that algebra, and existing qlib_snapshot/analyze_high52_unfilled_sources code
already uses it. Official collector blob82660f1112bdad3e3ba7fd22f3157228e13b67f5,
SHA2566b356884c76e170fde48e3ac58a4952a62d47705bcb2b7a344acd8f3798d7905,
is corroborating implementation metadata, not proof of the snapshot's exact
historical upstream vintage. No new data/network request or account/return.

Do not retry failed APIs, round an arbitrary ratio to cents, derive dividends
from factors, or manufacture ST/suspension/preclose/amount/arrival. Preserve all
earlier failures, fixed adaptive low-OP43names/24targets/95%weights/costs/gates.
This is conditional source reconstruction, not investment/PIT/account admission.

## Frozen arithmetic and empirical gate

Use exact Fraction arithmetic for closed IEEE754binary32 rounding cells bounded
by midpoints to adjacent finite32bit values. Positive finite OHLC/factor only;
volume allows zero with its cell intersected with nonnegative values. Reject
non-f32 inputs, negatives,NaN/Inf and cells adjacent to infinity. Apply fixed
relative2^-40guard to the ratio/product interval for finite64bit normalization
arithmetic. This guard is chosen before observations and cannot be widened.
For prices, enumerate integer cent ticks in the full interval. Exactly one
positive tick admits a conditional price; zero/multiple ticks are failures.

Authenticate only the physically capped qlib-price-delay-pre2026-clock-v2-20261021
provider whose calendar ends2025-12-31. Six fields(open,high,low,close,factor,
volume) for all43names and provider calendar/manifest/all-instrument metadata
must match original operating request7fedda231ca66593d9b1bfcf1c05f11f670fcc9ca18605c132f630885c65818c.
Also bind the complete preceding HTTP request/proof/capture context. Binary
extent and header must fit the capped calendar before decoding requested cells.
No2026feature float is decoded; hash bytes only for identity when authenticating.
Authenticate the actual calendar/feature byte buffers used for decoding and
recheck the complete frozen context immediately before the target boundary.

Controls are every original42packet/all20089source rows. Compare all four OHLC
for every explicitly trading raw row, including ST rows. Nontrading rows remain
counted and explicitly excluded from traded-price validation, never converted
to prices or trading status. Require every control issuer has trading rows and
every checked field has exactly one cent tick equal to independent raw price.
Record all failures. Only after that complete price gate may SZ002326quote
values be decoded. On failure there is no missing-code projection or fallback.

For volume, test exactly two prespecified unit scales,1and100shares/source unit,
against every control trading row's raw volume and product interval. A unique
scale consistent with every row identifies conditional units; none/multiple
remain unproved. This is input-unit calibration, never return-based selection.
Use floor(lower interval bound) as conservative conditional volume in shares;
do not choose a precise integer from an ambiguous cell. Price projection may
exist with unproved volume; aggregate source completion then remains false.

After a passing price gate, project all486explicit sessions for SZ002326.
Unavailable/ambiguous cells remain failures with no filled rows. Output source
kind is CONDITIONAL_F32_LATTICE_PRICES_NOT_RAW_VENDOR_OR_TRADABILITY. No account
input promotion follows even from all486conditional prices/volume lower bounds.

## Verification and continuation

New pure bounds module, narrow frozen runner and separate checker(no new producer
or bounds imports). Checker independently derives binary fractions from bit
sign/exponent/mantissa, every original/provider/method binding, all42control
results, unit hypotheses and permitted target projection. Hash inputs/output
tree through terminal persistence. Failures and partial outcomes remain immutable.
Bind intended artifact hashes at each write, rather than adopting a later tree.
Persist the complete control summary before target access; reserve each target
session before reading and persist each completed row separately. A failed read
retains its completed prefix, native error and explicit last session. The checker
reconstructs only that prefix and never continues the failed target projection.
One fresh code reviewer before actual request/run; one RED/GREEN correction pass,
full tests, no rereview. Push/verify remote freeze before first actual comparison.
Publish exact control/projection/check outcomes and all limitations. Only later
frozen primary/state/account work can establish holdings/ordered dependencies,
ST limits, tax treatment, corporate events and all lawful fractional branches.
2026stays exposed; no future outcome selects source or investment parameters.
