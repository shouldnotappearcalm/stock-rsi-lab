# Two official SZSE historical-catalog metadata probes

Previous turn made progress: Yahoo's original control has1939/1944price and
484/486volume matches. Strict gateFalse, target0; keep all failures unchanged.
Full goal remains2024>0,2025>0,2026Jan–Oct>=10%, not achieved. This is ordinary
read-only source discovery with installed curl, no new implementation feature.

The bound official trend page selects1815_stock_snapshot. Official report_new
static implementation constructs/api/report/ShowReport/data withSHOWTYPE,
CATALOGID,TABKEY,PAGENOand tab1PAGESIZE; its download branch also explicitly
recognizes1815_stock. The native kline caller has no date arguments; do not call
that current/history endpoint. Static metadata does not prove historical support.

Freeze exactly two GETs for these two catalogues, same existing controlSZ002153.
Both carry explicit2023-12-29..2025-12-31and code selectors (code/txtDMorJC),
TABKEYtab1,page1,size1000. Selector/date names are discovery hypotheses, not
validated parameters. One reservation per identity,20second total/10connect,
1MiB cap, no redirects/retry/credentials/TLSbypass/install/background work.
Publish/verify exact remote freeze before either call. Full previous proof input/
capture closure and primary metadata are bound. Preserve all raw/partial bytes,
headers, stderr, transport and native diagnostics; cancellation/storage failure
stops later requests. Verify all identities before/after publication.

Do not decode report data rows, dates or price/volume values even if HTTP200.
Only inspect report metadata key names, query condition identifiers/types and
column identifiers/labels; skip default/current/aggregate values and all data
arrays. Raw bodies stay local. This stage establishes query schema at most,
not historical coverage, source precision, PIT, company actions, state/tax/account
or investment returns. No target stock/no2026values/strategy changes. A later
frozen historical query must validate dates before any market values are used.
