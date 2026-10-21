# Existing liquidity candidate: 29 archived development sessions obtained

This source-only probe recovered actual archived minute records for every one
of the existing 29 rejected development sessions, but did not admit execution,
run a portfolio, change the investment method or produce a new 2026 return.
The three original annual return requirements remain unproven.

The request and code were pushed at
`d5ef5bce96f84c534ee8ce0b64cec602c71479a2` before acquisition. Exactly one LFS
batch and two object GETs were reserved. Both objects matched the pointer SHA256
and size from pinned dataset revision
`ba589a11534825044fe5a6b84838f50ba8d8d188`: 14,547,869 bytes in total.
All 16 bound inputs were unchanged, all 13 output hashes were audited, and all
source responses and selected original rows remain local. Private temporary
signed download actions were not published.

## What the archive actually establishes

| Source comparison | Passing sessions / 29 |
| --- | ---: |
| Exact sum of share volume against original daily source | 29 |
| Exact original daily open/high/low/close as decimal text | 3 / 2 / 5 / 1 |
| Original 240 closing-minute labels | 0 |
| All published prices on an exact cent grid | 0 |
| Original daily OHLC encoded as binary32, then compared exactly | 29 / 29 / 29 / 29 |

All 29 sessions have 241 records: the expected 240 closing-minute labels plus an
additional 09:30 record. Total selected rows are 6,989: 5,784 for SH603056 and 1,205
for SZ002505. None were deleted, shifted, interpolated or rounded. Of 27,956
published OHLC cells, 26,945 are not exact decimal cents.

The extra precision diagnostic encodes only the already-known daily reference
as IEEE754 binary32 and promotes it back to binary64. All 116 aggregate daily
OHLC values then agree exactly with the archive. This supports a representation
explanation; it does not authenticate the archive's unpublished providers or
prove its construction process. The original exact comparisons remain failed.
It is not a new normalization, source correction or admission decision.

The publisher does not disclose provider identities. The precise start/end
semantics and availability of each minute interval are not independently
certified. A time label is not an authenticated tradable event. The archive's
extra 09:30 record cannot simply be dropped to force the old 240-point validator
to pass. The earlier 2,247 admitted sessions and 29 rejected sessions remain
unchanged under their original gate.

## Reproducible independent audit

The independent audit uses no production source comparator, account, scorer or
network. It verifies frozen Git blobs, old 29-session selection, pointer/object
hashes and sizes, logical reservations, selected Parquet rows and JSON rows,
all per-session facts and untouched source inputs. Four negative controls
remove a session, alter daily volume, change a label and corrupt an object OID;
all are rejected. Logical reservation evidence is not independent packet-level
HTTP traffic measurement.

Root reran it with an identical report SHA:
`4531a6e5f3f0bc126f6653ac165d271233bf101eb5a5485418e8302847388ee3`.
Actual parser runtime was Python 3.11.15 / PyArrow 23.0.1. The 876-test full suite
passed locally and in the clean research environment; the latter skips four
optional integrations. Freeze CI passed all three jobs.

- [Frozen request](../../experiments/qlib/illiquidity-hf-archive-probe-request.json)
- [Every session's unchanged source comparisons](../../experiments/qlib/illiquidity-hf-archive-probe-results.json)
- [Independent audit](../../experiments/qlib/illiquidity-hf-archive-probe-independent-audit.json)
- [Run verification and output hashes](../../experiments/qlib/illiquidity-hf-archive-probe-run-verification.json)
- [Independent audit source](../../experiments/qlib/audit_sources/2026-10-22-illiquidity-hf-archive-probe-independent-audit.py)
- [Archive publisher](https://huggingface.co/datasets/neigezhu/china-a-share-1min-ohlcv)

## Next boundary

Define and independently review an explicit reversible cent-grid representation
contract and causal minute-clock interpretation before any archive execution
admission. Keep the original rejected source gate and failures unchanged. A
separate engineering interpretation must retain raw bytes, state assumptions,
reject unsupported prices/clocks and be frozen before running the unchanged
2024/2025 account. Do not use 2026 outcomes to choose that contract or alter alpha.

Whole immutable objects can contain later-year rows and Arrow may decode mixed
row groups internally. Only the 29 requested 2024/2025 sessions were exposed to
the comparator; this is not OS-level isolation. The discovery manifest also
records an unexpected mixed-year web-card preview. No sealed 2026 holdout is
claimed. Historical arrival, actual queues/impact, upstream provenance, full
October and investment profitability are not certified by this source probe.
