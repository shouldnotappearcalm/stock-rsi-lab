# Opaque Tencent transport results: both requests returned HTTP200

The previous goal turn made progress: exact float32 reconstruction was tested
and rejected, with seven price-cell failures and38 unit100 volume failures.
This turn pursued a different bounded raw source without changing the frozen
low-operating-profitability candidate or reading2026 investment outcomes.

The inspected [upstream collector](https://github.com/akfamily/akshare/blob/main/akshare/stock_feature/stock_hist_tx.py)
identifies the Tencent historical endpoint. Its exact blob/hash and unit claims
are preserved in the frozen request; its wrapper's start-year/latest queries,
yearly expansion, adjusted data and extra imports were not executed.

Request SHA256
`df89349583112972ae27471fd9a339aade7a2da7db4c0df64092b61c33275b37`
was published in commit`52d662bd0bc9fb86c58cadff4b32803a50ddc17c`; push and
exact remote head were confirmed before either network request. The installed
curl8.7.1 executed each exact frozen argv once, with20s total/10s connect limit,
1MiB cap, identity encoding, no retry/redirect/TLS bypass. Both requests specified
2023-12-29..2025-12-31,640rows, unadjusted data.

| Resource | curl exit | HTTP | Opaque bytes | Body SHA256 |
|---|---:|---:|---:|---|
| SH600118 control | 0 | 200 | 62029 | c2c1400f4c16d4baba3874fb1c19048963dd75deee48e133dc4015607ef01e50 |
| SZ002326 missing stock | 0 | 200 | 60869 | 59063522cb5e470d0ca42634f000ec4050c4f869ebb4eeb24e3c860418758798 |

Local originals are under
`data/local/qlib-pre2026-research-20261015/low-operating-tencent-opaque-pre2026-v1-20261023/`
in the main repository. Each resource has its reservation, request, headers,
opaque body, transport metadata, stderr and receipt. Raw responses remain local
because the server may attach unrequested current quote metadata.

Root reverified all600 bound inputs including the request and installed curl,
all15 artifacts, exact resource URLs/date arguments, reservations, exit statuses,
effective URLs, response lengths and preserved hashes. The receipt check passed
only identity/transport verification. Terminal/check public copies are byte
identical to local originals; body values were not parsed or printed.

Additional byte-prefix inspection found both responses use the expected
`kline_day2023={` assignment, not HTML-document framing, despite text/html
response headers. This check decoded no body values and admitted no bars.
Its separate receipt is `low-operating-tencent-framing-preflight.json`.
No user/system curlrc or CURL_HOME/XDG_CONFIG_HOME override was present at the
read-only postflight check. These checks do not replace historical-row validation.

- Terminal SHA256: `1c103c6e9bfcfc1a3a366719f6606db0f62599ae4cf3e943de2e92d1ca99ae13`.
- Check SHA256: `a326865a8f0a02b092d06839d06565f31803f7f19b06c9875296cea696d4f701`.

HTTP200 and plausible byte counts do not establish the returned schema, stock
identity, historical coverage or data correctness. Accepted bar rows remain0.
No source/account/PIT/tax/action/return admission follows. No runtime software
or strategy behavior changed; this was two read-only source requests with frozen
arguments and research artifacts. No dependency installation or background job.

Next required work is a separately frozen selective historical decoder. It must
skip unrelated response values without decoding them, check each selected date
before reading quote values, reject out-of-range/adjusted/malformed rows, verify
the existing control's OHLC and units, and retain partial/failed evidence. Only
then can target coverage be assessed; missing ST/actions/arrival evidence still
requires separate resolution. All prior SDK/HTTP/f32 failures and full objective
2024>0,2025>0,2026Jan–Oct>=10% remain unchanged. The objective is not achieved.
