# Fixed12 initial2022 annual filing metadata capture

The objective stays2024>0,2025>0,2026January–October>=10%. The prior financial
vintage prototype passed its two-report source regression; no strategy or new
return was computed. This step supplies the initial original filing identities
needed before a2024 investment test. A2022 comparative column first published
in2024 cannot be substituted into an earlier snapshot.

## Frozen sample and existing sources

Use exactly the12 codes in the preexisting fixed-hash
`fundamental-value-pilot-capture-request.json`, preserving order. No change by
price, accounting value, return, industry outcome or2026 evidence. The sample
includes different accounting businesses and is a data pilot, not an investable
universe or certified nonfinancial sample. Existing501-name announcement metadata
is stored under `cninfo-csi500-reports-20261017`; only the12 named packets are
read. Authenticate its manifest/plan and their per-code hashes. Reuse its captured
`org_by_code` mapping only for endpoint addressing; it is a current mapping,
not a historical security master.

The existing2024–2025 metadata inventory has24 ordinary full annual reports for
fiscal2023/2024 plus one visual presentation edition. The SH6035172023 title
uses`2023年度报告全文`; preserve this variant. The SZ0007832023可视版 remains
separate and is not silently chosen as the ordinary financial report. This
inventory only establishes metadata presence, not PDF bytes or financial data.
Initial fiscal2022 originals are outside that old publication window.

## Exact new source request

Freeze and push `profitability-fixed12-initial-metadata-request.json` before
network. Twelve logical attempts only, one per code; no retry/resume or automatic
endpoint fallback. POST the existing official endpoint
`https://www.cninfo.com.cn/new/hisAnnouncement/query` with each fixed code/org,
category`category_ndbg_szsh`, window2023January1–December31, pageNum1/pageSize30.
The exact resource dictionary and two method hashes are in the request.

Use the new `immutable_http_capture.py`; do not call the older retrying client.
Persist request and budget reservation before opening the network, fsync files,
retain raw HTTP body and response metadata/hash/time. Content-Length mismatch,
oversize, redirect outside the original HTTPS host, duplicate resource identity,
interruption and semantic rejection do not trigger a second call. Max raw body
1MiB; timeout20seconds; minimum spacing0.2seconds. These are logical attempts,
not an independently observed count of DNS/TCP/TLS or redirect wire exchanges.
The raw error page or oversize prefix remains evidence, not an admitted response.
Evidence-write errors are fatal and preserve the original exception.

A response requires exactly one complete metadata page, at most30 rows, and no
hasMore page. Every row must match code and2023 publication date, with a unique
announcement identity. Preserve all normalized rows. Classify summaries,
English/visual editions separately. Select one or two full2022 annual report
metadata rows by explicit title schema, including ordinary full-text and known
revised/corrected suffixes; retain all selected editions, never choose by numeric
values. Require safe `finalpage/date/id.PDF` paths tied to the announcement ID.
A missing/ambiguous/unsupported source leaves that issuer rejected. Three
consecutive source rejections stop remaining requests and retain pending names.
No broad category fallback or extra-page request is implied.

## Run and state transitions

`scripts/capture_profitability_initial_annual_metadata.py` verifies the frozen
request, sample, inventory, old capture plan/manifest/12packets and method bytes.
Output must be the previously nonexistent fixed source subdirectory
`gross-profitability-initial2022-metadata-20261022`; no fresh-path budget reset.
The new acquisition writes only there, and always rechecks every input and the
request afterward. An interruption/error preserves the first exception and
terminal record. No successful summary after input mutation or evidence failure.

The HTTP directory retains each request/reservation/body/response; each issuer
gets a classification packet. Root input-before/postcheck, case_results, terminal
and summary distinguish complete versus source-incomplete. Exit0 requires all12
issuer metadata captures; source-incomplete gives exit2, and an interrupted or
three-failure stop preserves its nonzero failure. All failures stay immutable.

No PDF download, new numeric financial data, price, ranking, account or return
scorer is allowed in this request. Successful metadata is not factor admission.
Whole-version history, historical nonfinancial identities and exact arrival
remain uncertified. Nominal announcement timestamps at midnight remain dates,
not an intraday availability guarantee.

## Verification and next step

Behavior tests check reservation-before-fetch, one attempt, original byte/error
retention, interrupted and truncated/oversize responses, unsafe redirects,
metadata page/code/date/path/title/duplicate guards, all12 completion, three
rejection stop, existing-output protection and source/request mutation after
interruption. Run the full unittest suite and verify the pushed commit's CI.
After the actual source terminal, independently inspect raw metadata versus
selected filing identities and all input/output hashes.

Then separately freeze a PDF request using the discovered URLs plus original
2023/2024 metadata, reusing the two already authenticated SH600166 PDFs. Download
only the declared document set into a new directory with a finite budget. Retain
visual/correction metadata and any unsupported accounting schema without deleting
or changing companies. Parse and verify the fixed12 source sample before planning
whole-universe coverage and a separately registered2024/2025 profitability trial.
No2026 output is permitted to choose the method. No result here satisfies or
narrows the investment objective.
