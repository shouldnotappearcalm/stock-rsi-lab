# Selective Yahoo pre2026 component projection

Previous turn progressed: strict Tencent volume rejection retained. This turn's
two bounded Yahoo GETs returned HTTP200 with44844/44989opaque bytes. No Yahoo
date or quote values have been decoded. Full goal remains2024>0,2025>0,
2026Jan–Oct>=10%, unachieved. Same low-OP43names/24targets/95%weights/costs.
Direct implementation/public push authorization persists; native execution in
the existing pead worktree, one fresh final reviewer, one tested correction pass.

Approaches: do not infer a Tencent tolerance from observed disagreements. Test
the independently acquired Yahoo response instead, using a small selective
projector. Avoid yfinance's default auto_adjust/repair/current metadata wrapper.
This new source hypothesis does not amend any earlier frozen source gate.

Use the frozen1MiB JsonSlices walker to select chart.error(null), exactly one
chart.result, meta.symbol and exchangeTimezoneName(Asia/Shanghai), timestamp,
and indicators.quote(exactly one object). Ignore all other/current/adjclose/event
values without decoding them. Validate the entire timestamp sequence BEFORE
reading any quote scalar: integer Unix seconds,09:30Asia/Shanghai, unique ascending
canonical dates in the fixed486sessions/2023-12-29..2025-12-31. No earlier-prefix
quarantine or later/offcalendar acceptance. Reject duplicate traversed keys,
wrong issuer/zone and inconsistent array lengths. Null OHLC/volume is failure.

Prices must either be exact positive cents in the original decimal token, or
shortest-roundtrip binary64 representations of exact finite positive binary32
values whose closed neighboring midpoint cell contains exactly one positive
cent. No factor, epsilon, guard, automatic adjustment or repair. Retain original
selected scalar tokens with every projected row. This tests an explicit native
float32 representation hypothesis, not a guaranteed Yahoo provider format.
Volume must be a nonnegative integer token in shares, no scaling or tolerance.
Amount/state/preclose/actions/arrival remain unknown, never filled. Yahoo native
prices may be split-adjusted: control agreement is required but does not prove
target corporate-action completeness or historical raw/share semantics.

Compare every original trading control OHLC/volume exactly (including ST rows)
using the unchanged frozen comparison. Persist every completed row immediately;
only a complete passing SH600118 comparison allows target-start marker, full
input/output identity recheck, authenticated target-buffer load, second recheck,
then SZ002326 decoder. An error retains durable numeric prefixes and native
diagnostics; zero completed prefix must not continue numeric reads during audit.
Use the frozen per-write/postpublication finalizer, no network or account run.

Audit uses the same selective projector (explicitly NOT independent decoding),
the separate frozen control comparator, durable row/aggregate/marker/count
reconciliation, full source/request/method hashes and artifact closure. Validate
control rows, summary and aggregate before any target read, even on native error.
Root also rehashes every input/output/public copy. No independent parser/window
guarantee: inherited ignored-string UTF-8/depth65-empty-container limitations stay.
Catchable interruption is covered; no uncatchable/storage-failure guarantee.

Freeze and push request/methods/spec/plan/review; verify exact remote before first
Yahoo date/quote scan. Preserve opaque acquisition and all earlier failures.
Publish only historical selected JSON records/checks, not raw bodies/current
metadata. Source/account admission,2026qualification and full goal stayFalse.
