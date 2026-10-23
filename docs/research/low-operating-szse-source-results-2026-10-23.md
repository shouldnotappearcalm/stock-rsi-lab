# Official SZSE history route and one-row precision results

Goal remains one continuous frozen account with2024>0,2025>0,2026Jan–Oct>=10%,
unachieved. Previous goal turn made progress: actual Yahoo control discrepancies
and official SZSE static route metadata. Current work used read-only existing
curl/JsonSlices/numeric/scale primitives; no production code change, installation,
broker action, background task, strategy edit or return computation.

## Real queries

Freezeefd540540c40a6864e84bf61b9ca71c10e8306b2and its exact remote were verified
before two registered GETs, requestSHA
4fae7ab327b8ee6211df4153954b509ca00f09d1feda9043bf14d0972bd2def4.
Both HTTP200,3405/3439bytes.1815_stock_snapshot rejected the long interval with a
five-day query limit;1815_stock returned one row. No retry or target query.
Metadata confirms txtDMorJC/txtBeginDate; snapshot also txtEndDate/archiveDate,
history instead txtHistoryMaxDate. Do not assume the history end filter worked.
Columns declare OHLC/preclose, volume in10000shares, amount in10000CNY. Neither
report has explanatory notes. Report rows were opaque during metadata inspection.
Reading native service errors extended that diagnostic only to availability
errors; the original acquisition terminal's opaque state remains literal.

## Date-first one-row probe

Freezee51279aee2a5fd8f04563c9ed045add57b7f8db7and exact remote verified before
one retained-row inspection, requestSHA
894c7db424d4a077cdde79bbca3677dad514794a65be11c149ca23e7d795b461.
Zero further HTTP. Decode only jyrq/zqdm first: exact2023-12-29and002153, then7
selected market scalars. OHLCandpreclose all match independent original packet.
Native volume714.18(10000shares) maps to7141800; original is7141836. Native amount
6937.33(10000CNY) maps to69373300; original is69373371.66. Original token grouping
and precision are retained. This proves neither an exact-volume source nor a
rounding law; no tolerances or invented extra decimals were introduced.

The official route can return at least this historical control row; one row is
not486-session coverage or a full source acceptance. All rejected Tencent/Yahoo/
f32/HTTP/SDKattempts remain unchanged. Missing targetSZ002326not read, no2026quote
values, no full dataset/state/actions/arrival/tax/account admission and no return.
User-approved fractional-stock allocations still require all lawful branches.

Root verified1661metadata-stage inputs/15captured artifacts and1679one-row inputs,
plus byte-identical public projection. Raw report bodies remain local. This is
root reconstruction using shared existing primitives, not an independent decoder
review or full JSON guarantee. No code changed, so no new local full-suite run
was needed; existing1505-test evidence belongs to the unchanged code. Final
remote CI must be verified for the publication head.

Next source step: inspect the official XLSX export linked by the already bound
report implementation, under a separate exact one-control/date request. Do not
assert it has more precision before inspecting original numeric XML/cells. This
may still be display-rounded. If so, investigate a documented source precision
contract or another exact source, retaining every strict rejection. No strategy
selection may use exposed2026 outcomes.
