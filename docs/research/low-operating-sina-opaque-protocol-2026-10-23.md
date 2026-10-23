# Two opaque native Sina daily-JSON attempts

Previous source stages made progress but remain rejected. Official SZSE XLSX
stores volume714.18/amount6937.33as inline text, no hidden higher precision.
The full continuous-account goal2024>0,2025>0,2026Jan–Oct>=10% is unachieved.
Candidate43names/24targets/95%weights/costs unchanged; all failed sources retained.

Inspected AKShare original stock_zh_a_sina/cons and existing local data-interface
implementation identify native Sina Kline routes. The compressed full-history
wrapper and forward-fill/adjustment/current-info flows are not called. Existing
local source maps daily toscale240and the nativeJSONURL below; this is endpoint
metadata only, not a reuse of any investment skill or verified availability.

Freeze two exact nativeJSONGETs, existingcontrolSH600118then missingSZ002326,
scale240,ma=no,datalen1023, installedcurl only. One reservation each,20total/
10connectseconds/1MiB cap, no retry, redirect, credentials, TLSbypass or install.
The API exposes no validated historical end parameter: requested recent-history
raw responses MAY contain2026and earlier rows. Keep the entire body local/opaque;
no JSON list/date/quote parsing in this acquisition. No latest quote endpoint.

A later separately frozen/reviewed decoder must check canonical unique ordered
date tokens, quarantine every outside2023-12-29..2025-12-31row without decoding
its quote/volume values, and require all486explicit sessions. The original strict
price/integer-share-volume control gate remains exact; only complete control
agreement allows target value projection. This is a new source-specific date
selector, not a modification of earlier frozen Tencent/Yahoo failure gates.
Never run the local wrapper's broad parsing, retries, ffill or current defaults.

Bind all earlier inputs/captures, current upstream/local metadata and protocol;
publish and verify exact remote before eitherGET. Persist raw/partial bytes,
headers, native stderr/status, reservations and immediate hashes; cancellation
or storage failure stops later requests. Finalizer verifies full input/output
identities through publication. Acquisition accepts zero rows, no source/PIT/
state/action/tax/account admission, no2026values or return/strategy selection.
