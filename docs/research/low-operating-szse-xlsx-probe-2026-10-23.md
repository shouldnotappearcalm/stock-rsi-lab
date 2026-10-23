# Official single-control XLSX precision probe

Previous goal turn progressed: one official historical row has exactOHLC/preclose,
but displayed volume/amount differ from raw controls. Full goal remains2024>0,
2025>0,2026Jan–Oct>=10%, unachieved. Keep all previous source rejections and fixed
low-OP43names/24targets/95%weights/costs unchanged. No2026outcome tuning.

Official bound report_new implementation's export URL usesShowReport and
SHOWTYPE=XLSX. Freeze one exact GET for1815_stock,tab1,existingcontrol002153,
txtBeginDate2023-12-29,txtHistoryMaxDate2025-12-31,page1,size1000. Date/control
semantics validated only for the priorJSONrow; never assume export honors them.
One durable reservation,20secondtotal/10connect/1MiB cap, no retry, redirect,
TLSbypass, credentials, installs or background work. Verify exact remote freeze
and full inherited input hashes before network. Preserve partial/raw bytes and
native transport; cancellation or persistence failure aborts. No target request.

Inspect read-only with bundledPython3.12stdlib because original XML numeric tokens
and a date-first cell boundary are required; generic workbook import may coerce
numbers or materialize ignored future values. No authoring/export/render/change.
Accept ZIP/XLSXonly, <=50entries, <=4MiBuncompressed total, <=1MiBperentry; reject
external relationships, macros, formulas in selected cells, duplicate/invalid
cell refs, unsupported formats. Do not extract ZIP contents to filesystem.
Inspect only structural workbook/sheet metadata, header cells, first-column date
and second-column security cells before any financial scalar. Require one sheet,
recognized date/security headers and exactly one2023-12-29/002153data row. Numeric
security2153may become six-digit002153; no other identifier coercion. Any other
or future date/issuer rejects before prices/volume/amount. Shared strings remain
raw XMLslices until selected; never enumerate full decoded workbook values.

Then inspect raw selected OHLC/preclose/volume/amount cell tokens/types/styles,
not rendered numbers. Unit labels must confirm10000shares and10000CNY. Parse exact
Decimal, standard thousands grouping only, no precision invented or tolerance.
Compare all7components to the bound original raw control. Separate stored scalar
precision from number-format display. Keep headers/formats/identity and selected
historical evidence; no raw workbook/public future contents. Source coverage,
provider precision guarantee, PIT/state/actions/tax/account and returns remain
unadmitted even if this one row passes. Preserve any rejection unchanged.
