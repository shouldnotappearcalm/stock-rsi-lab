# Complete annual-source V6 inspection

This result concerns source reconstruction for the gross-profitability family,
not a new investment return. The objective remains one frozen strategy and
continuous account:2024>0,2025>0,2026January–October>=10%. October is not complete.
No2026 financial/market values or returns are used for method selection here.
Earlier exposed2026 data cannot become a fresh sealed holdout by relabelling.

## Frozen scope and method

The request is `experiments/qlib/profitability-all1236-v6-request.json`,SHA256
`fc7ddecfac53f0d478180ecac7013f1dc6fe8460cc2be41fed7571d0418870f9`, pushed at
`faf9434ee92c19ec1299f0c9206708376b23fd30` before extraction. It covers1236
original announcement candidates over the dated394 issuer source range:
408 authenticated initial caches and828 later originals. All editions, explicit
failures and source gaps are retained. No parse-success investment pool is created.

V6 returns V5 parser successes verbatim and protects182 known old reports. It
adds only explicitly labelled
CAS19Article4 currency inference from a bounded affirmative Chinese-CAS
financial-statement compliance declaration and the archived official historical
reference. This is neither a literal人民币 quote nor certification of actual
issuer compliance. Local units must still be literal; Jan1 balances do not become
priorDec31 observations. No header/financial-field proxy extension in this run.

## Actual result

All1236 source cases completed with all10362 inputs unchanged. All828 later
originals produced page caches; all182 protected old reports retained identical
complete observations. The output directory contains2378 files.

| Source result | Documents |
| --- | ---: |
| Three literal consolidated fields parsed, pending visual/accounting review |665|
| Unsupported source schema |511|
| Cover/company identity not verified |60|

There are1103 annual observations across270 issuers.162 reports use explicitly
labelled CAS19 regulatory currency inference. Only126 issuers have supported
current-year reports in all2022/2023/2024; this is not an admitted investment pool.
For the same initial408 corpus, supported reports increased174→249 while all
old observations stayed identical. Later828 candidates have416 supported reports.

By report fiscal year,2022 has251 supported/141 schema/20 identity cases,2023
has259/130/22,and2024 has153/236/18. Older reissued report editions remain in the
complete corpus. SH has436 supported/221 schema/36 identity cases; SZ229/290/24.
Parsing therefore still has substantial format/coverage asymmetry. The largest
schema failures are170 two-fiscal-column headers,100 scoped CAS declarations,
63 revenue row blocks and60 consolidated/parent boundary cases. They are not
imputed or removed from the dated source range.

The completed separate QA passed:483 newly checked supported reports,2310
literal monetary cells and3808 directly redecoded original PDF pages. All182
old report observations and all10362 inputs are unchanged; all2378 output
files were inventoried before and after QA. Full local unittest discovery passed
1061 tests,including the seven new checker regressions. Public summary/audit
files are byte-identical copies of actual local outputs:
`profitability-all1236-v6-results.json` and
`profitability-all1236-v6-source-audit.json`.

The first two QA attempts failed because the QA
incorrectly applied V2-style identity scope and required a header to be unique
across all continuation pages. The checker now reconstructs the existing V3
cover-first/issuer-information scope and validates an exact header on its selected
consolidated page,allowing normal repeated continuation headers. Seven regression
cases cover these boundaries,including rejecting parent-page/substrings and
out-of-window/wrong-year identity. Both failed QA logs and red test logs are
retained under the separate local QA evidence folder,with hashes in
`profitability-all1236-v6-checker-validation-history.json`; frozen source output,
parser,request and old failures are unchanged.

## CI correction

The freeze push exposed a missing declared test dependency: the new whole-source
test imports`pypdf`, while CI installed only BeautifulSoup. The shared requirements
now pin`pypdf==6.10.0`. Exact local discovery without the bundled-package
bootstrap reproduced the import failure. With the existing package,1054 local
tests passed. The hosted clean Python3.11/3.12 and numerical jobs all passed at
`f49a82664757e7c357d04aa219eaa7bf1c9a1276`,run39685759553. No tests or notifications
were disabled; frozen methods and inputs remain unchanged.

## Separate missing-source research

An uncategorized,2025-only CNINFO metadata query for SH603737 still returned only
the2024 summary. The issuer's2025 shareholder-meeting materials point to SSE:
[2024 annual report publication reference](https://static.cninfo.com.cn/finalpage/2025-05-10/1223510425.PDF).
A separate official SSE metadata query on2025April26 identified the full report
at`603737_20250426_SX7A.pdf`. Its HTTP200 PDF-location response redirected to
static.sse.com.cn and contained gzipped HTML,so it was rejected and retained.
The CNINFO-only capture class also rejected the SSE host before any network;
that preflight failure is retained separately from the one actual SSE GET.
No original financial values or identity were admitted from this response.

Metadata,failed responses and source hashes are in the separate public research
record`profitability-SH603737-2024-full-report-gap-research.json`,with original
bytes kept locally. This discovery does not mutate the current1236 inputs or
pretend the gap is repaired. SZ002505's FY2024 full report remains unresolved.

## Evidence limits and next investment step

A passed source check is not a profitable strategy. Historical captures remain
2026 arrivals. Default observed-time availability does not backfill them into
2024/2025; publication-day-end reconstruction is conditional and explicitly lacks
actual arrival proof. Complete financial-version history, accounting/business
compatibility and full numeric visual review remain separate requirements.
The separate checker shares pypdf and was written by the same researcher after
run start; it does not independently replicate the entire source grammar.

Resolve remaining primary-source/format/identity and accounting-version gaps,
then freeze the GP policy and equal-budget controls for2024/2025 continuous-account
development. Only an unchanged qualified development candidate can proceed to
2026 diagnostics. No claim that the three economic objectives are satisfied.
