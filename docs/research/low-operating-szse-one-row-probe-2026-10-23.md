# One retained SZSE control row: date-first precision probe

Previous metadata probe returned HTTP200twice.1815_stock_snapshot rejected the
long interval with a five-day maximum;1815_stock returned one opaque data row.
It exposes txtBeginDate, not txtEndDate, plus txtHistoryMaxDate. This does not
prove the supplied end filter was honored. Preserve both original requests.
Only metadata/column labels and native service errors were read; one row's
security/date/values remain unparsed. Reading the native service error extended
the metadata-only diagnostic to availability errors, never market data; cost:
the original opaque terminal describes acquisition, not the later inspection.

Freeze one read-only inspection of the retained1815_stock response. No new HTTP,
no new implementation feature. Use the existing frozen JsonSlices/numeric/scale
primitives. Require exactly one report, matching catalogue, null error and one
row. First decode only jyrq and zqdm: require exact2023-12-29and002153. Reject any
other/future date or issuer before reading any price/volume/amount scalar. Then
select ks/zg/zd/ss/cjgs/cjje/qss only, retain raw token text/hash, reject nonfinite,
negative values or subcent OHLC. Unit declarations are directly from bound
metadata: volume10000shares,amount10000CNY; compare OHLC/volume/preclose/amount
exactly against the bound original486-session raw packet's same date. Commas may
only be removed after validating standard thousands grouping of numeric strings;
no arbitrary HTML stripping, epsilon, fill, adjustment or inferred rounding.

This is a one-row source precision/coverage lead, not validation of a historical
route, target dataset, arrival/actions/state/tax/account or return. No target
stock data,2026values, strategy/weights/cost changes. Freeze/push/verify remote
before first row-date/quote scalar inspection. Bind full previous proof closure,
actual raw source, parser methods and protocol. Preserve any rejection unchanged.
