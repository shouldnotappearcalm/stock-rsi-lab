# Same-policy monthly annual-source visibility through October 2026

Implement the next source gate from the completed
[original-cell review](asset-expansion-2026-assets-results-2026-10-23.md).
The full objective stays 2024 > 0, 2025 > 0 and 2026 January–October >= 10%
under the frozen strategy and continuous account. This gate does not rank
securities, read market values or calculate an account result.

Add `src/stock_rsi/asset_availability.py` with
`snapshot_availability(documents, case_reader, industry, cohort, as_of, *,
mode=OBSERVED)`. Preserve `profitability_availability.py` and its 2025 cap.
The new API supports only clocks through 2026-10-21 15:05 Asia/Shanghai.
Check publication-day-end and actual observed capture before annual identities
or case payloads; default OBSERVED remains distinct from explicit publication
reconstruction. Retain every member of the initial 394-name cohort, including
missing/financial/unknown industry classifications from the unchanged 2021Q3
catalog. Never claim that catalog proves current business identities.

Select fiscal year before publication day, exactly as the earlier metadata
selector did. Preserve same-day different-byte ambiguity. For identical-byte
editions retain all identities and use the smallest numeric announcement ID
as the deterministic witness. Read only the selected visible case. Unsupported
cover/table/PDF cases produce no report and block older values. A supported
selected case must match issuer, year, publication, observed arrival, document
hash and announcement ID. Validate the asset report and expose its record ID
and explicit period identities, not monetary values or an investment score.

Add `scripts/build_asset_availability_2026.py` to join all original 1,236 asset
cases with the 400 newly inspected annual candidates. The request must bind
the immutable parent requests/audits, complete asset outputs, industry source,
legacy monthly views, the same dated membership file, explicit formation
calendar, methods and tests. Keep every edition, including all failed cases;
no PDF or network read is needed. Literal-cover resolution is allowed only
where an existing authenticated case already resolved a yearless title.

Derive 34 monthly formation/execution pairs from the existing explicit Qlib
calendar and validate that the original 24 pairs are unchanged. That calendar
ends October 13; it establishes October's first session but does not establish
all sessions or quotes through October 21. Save both modes for all 34 pairs,
68 complete 394-issuer queries. For all 48 pre-2026 mode/formation queries,
compare the new metadata selection and industry fields with the immutable old
views. Asset parse statuses may differ from gross-profitability parse statuses;
do not require false equality between those independently parsed facts.

Tests in `tests/test_asset_availability.py` cover old-selector parity,
future-payload independence, day-end and observed-arrival boundaries, same-day
conflict/deduplication, later failure/current-only handling and source identity
corruption. `tests/test_asset_availability_runner.py` cover explicit-session
formations, complete cohort/modes, parity refusal, interruption, changed-input
postchecks and fresh-output-only behavior. Run the full repository suite.

Freeze and push the request/method hashes before evaluating actual monthly
2026 source views. The foreground runner writes immutable query files plus
before/posthashes, completed/pending queries and original errors; it never
overwrites, resumes or silently repairs a failed run. A separate stdlib checker
must reconstruct all clocks, selected editions, case/report bindings, source
limits, summaries and old-window parity without importing this selector.

After source QA, freeze the unchanged 2026 ranking/session/quote/action
extension. Do not change freshness, minimum 100 eligible names, decile, 95%
exposure, capital, cost profiles or allocation/tax rules from the 2026 views.
This source gate cannot prove that every formation has enough eligible names.
The observed historical feed, complete revisions and investment admission stay
unverified, and previously exposed 2026 evidence remains unsealed.
