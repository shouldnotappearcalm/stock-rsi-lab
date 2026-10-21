# Fixed development-source probe: two public minute archives

Continue the existing `amihud22` source-completion route. This is not a new
alpha candidate or another 2026 portfolio test. The unchanged development
admission has 29 rejected sessions: 24 for SH603056 and five for SZ002505.
Prior TDX and BaoStock failures, sources, signal, targets and gates remain intact.

The public dataset [china-a-share-1min-ohlcv](https://huggingface.co/datasets/neigezhu/china-a-share-1min-ohlcv)
has per-instrument archives for both names. A read-only Git clone with LFS
smudge disabled authenticated its metadata at commit
`ba589a11534825044fe5a6b84838f50ba8d8d188`. No price object was downloaded during
metadata discovery. The two LFS pointers bind 5,822,238 and 8,725,631 bytes,
respectively; the full objects must match their exact SHA256 and size.

## Freeze before acquisition

`scripts/probe_hf_illiquidity_minutes_pre2026.py` accepts only the frozen two
objects and the exact 29 exceptions from the previous admission. Reserve at
most one read-only LFS download batch and one GET per object, three logical
requests total. There are no free retries or automatic route substitutions.
Persist raw objects even if the checksum or subsequent parser fails. Temporary
signed download actions stay in a local private response; public receipts expose
no action URL query or header values. Preserve reservations, errors and all
input postchecks, including interruption and initial output-write failure.

`selected_parquet_rows` applies the explicit development-session filters before
Python rows are materialized. The immutable whole file may contain later-year
prices; Arrow may internally decode a mixed row group. This is not OS-level
future-data isolation. The comparator receives only requested 2024/2025 dates,
and source rows are retained locally without price rounding or timestamp shifts.
A perturbation fixture changes 2026 values while preserving identical development
comparison facts.

Report every session's observed labels, OHLCV comparisons against the original
raw daily packet and exact-cent checks. Do not drop a 09:30 record, manufacture
09:31 labels, interpolate missing rows, normalize volume to match, round a
near-cent price, modify the original daily data, or run a portfolio. A numeric
match cannot itself admit this source: upstream providers are undisclosed and
bar interval semantics have not been independently authenticated. Admission
therefore remains false under every probe outcome.

## Evidence and exposure

[Discovery manifest](../../experiments/qlib/illiquidity-hf-archive-metadata-discovery.json)
binds the metadata, original Git blob identities and both LFS pointers.
[Request](../../experiments/qlib/illiquidity-hf-archive-probe-request.json)
binds methods, original daily packets and all 29 dates. The prospective output
is `illiquidity-hf-archive-probe-20261021/` in the existing local research root.

The search tool unexpectedly returned the dataset card's mixed-year sample
preview, including unrelated 2026 BJ rows. That incidental exposure is recorded;
it was not used to select the pre-existing two names, 29 dates, strategy or
parameters. The consumed year is not called a sealed holdout. No new portfolio
return is computed, and the three original investment conditions remain unmet.
