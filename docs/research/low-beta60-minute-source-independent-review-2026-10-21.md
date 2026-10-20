# Fresh final source-stage code review — 2026-10-21

Reviewed base f5d09f2229e3cb15d3fbcc46ce13b7519fe962b7 through HEAD 8086d2e069b51b465d935137dd0ee3e718aae479, plus the explicitly supplied untracked independent audit script (SHA256 09b074532a08301e274008bb289aaa886fe983db6e14fcb0c7c18560b1db301b). Read-only checkout/index/HEAD/source evidence. Reviewer wrote only /tmp artifacts. No source network calls, no account runs, no 2026 research-market or returns files opened. For precision: the installed SDK historical-minute documentation itself contained a 2026 illustrative sample; it was encountered while checking the documented hand unit and was not used as research evidence.

## Strengths and verified evidence

- All nine new capture/admission tests independently passed. They exercise useful restart, corruption, failure, identity and quantity behaviors.
- Re-ran actual complete local admission to /tmp/lowbeta-final-review-local-admission-20261021, exit 0. Both summary and details are byte-identical to the supplied run. Summary SHA256 24fd697156e7140c463b54d577782b2a04a4fabe6effb0467556a51c43c8ed63; details SHA256 3bde160cec1a606536d127632d965c342a41a190ea0764bfe62260a152402f63.
- Read and independently re-ran the supplied stdlib audit, exit 0. /tmp/lowbeta-final-review-independent-replay-20261021.json is byte-identical to the original audit, SHA256 1388eee27dfbc219363d27f68a9b1b954bc80c5c88f379a58dad586a3d4ca2be. It reconstructs 1332 prefix pairs, 839 original reused packets, 493 requests/reservations/responses, 319680 points and 63936 evidence windows; all five arithmetic/identity semantic negative controls reject without relying on file hashes.
- Existing inspect_minutes and aggregate_minutes are unchanged in the review diff. Capture and admission preserve source failure and incomplete-prefix distinctions, with candidate_promoted/objective_achieved false.
- Independently calculated all source total differences: only 100 exact-share matches, but all 1332 nearest-hand totals match; reported-share minus raw-day-share range is [-49,+50]. No unexplained large aggregate volume discrepancy was found. This supports the stated daily hand-rounding diagnostic; it does not certify per-minute exact shares or a market-observed fill-capacity lower bound.

## Findings

### Critical

None found.

### Important — P2: restart silently rebinds mutated artifact bytes

File: scripts/capture_low_beta60_minutes_pre2026.py:36-37,49,61-72 (the new wrapper's uses of unchanged write_packet_once).

A completed or partial run is resumed without first authenticating its existing manifest/snapshots and their bound file bytes. write_packet_once compares parsed JSON, so formatting mutations are accepted. Reproduction: capture a one-item fixture; append a newline to sessions/SH600001-2024-01-02.json; resume with the same plan/request. Resume succeeds with complete_capture=true and rewrites manifest.per_session_sha256 to the changed hash. Appending a newline to plan.json or capture_request.json similarly succeeds and rebinds their hashes. Appending a newline to a journal request or capture snapshot is also accepted, and a changed manifest is overwritten. A semantic session payload mutation correctly rejects, so this is specifically an untested byte-integrity gap rather than repeated-fetch behavior.

Impact: the stage promises original-byte immutability and restart verification. A resume currently launders byte changes into new evidence instead of failing closed. The frozen actual 1332-packet capture currently passes all original hash chains; this finding is not evidence that that run was tampered with. Source calls were not repeated in the negative controls.

Recommendation: before any source callback, verify prior checkpoint/snapshot consistency and every existing plan/request/session/journal artifact against its original byte binding or deterministic canonical writer bytes. Preserve existing frozen v1 code/plan/source evidence; a separately versioned supported resumption entrypoint is a reasonable correction. With existing reservations or packets but no authentic checkpoint, stop conservatively. Add byte-only tamper controls and unchanged-byte resume tests. Do not change shared old helpers or reinterpret original method hashes.

Reproduction artifacts: /tmp/lowbeta-final-review-negative-controls.py, /tmp/lowbeta-final-review-negative-controls.json, /tmp/lowbeta-final-review-additional-tamper.json.

### Minor — P3: exported capture_prefix lacks the absolute 493 guard

File: scripts/capture_low_beta60_minutes_pre2026.py:25-28,38.

The function only compares the caller's max_fresh_query_reservations with len(fresh); a new 494-item request with a matching 494 budget reaches fetch. Reproduced with a synthetic callback that immediately raises KeyboardInterrupt, with no real source IO. The production CLI authenticate() hard-codes 493 and protects the actual run, so this is not an observed production budget overrun.

Recommendation: also reject len(fresh)>493 in the supported wrapper/API, while retaining small fixture budgets. Keep the CLI's exact493 check. Include a matching494-budget test, not only mismatched-budget tests.

## Proposed v2 follow-through considerations

The proposed separate v2 entrypoint can preserve historical evidence and close these findings. Its preflight must verify all existing fresh journal requests/reservations/responses, including artifacts not yet covered by the last session manifest after an interrupted write. A check of only manifest-covered sessions is insufficient. Existing request.json bytes need a binding or deterministic byte comparison: the current minute packet omits QueryJournal's request_sha256 receipt even though it retains reservation and response hashes. Existing failed response receipts must receive the same checks as successes. The no-checkpoint-with-existing-state rule is conservative and appropriate. Clearly mark v1 as the historical frozen capture implementation and route supported continuation to v2. No further source fetch is needed to fix or validate the completed capture. This paragraph evaluates the proposed design, not an implementation that was absent from the reviewed HEAD.

## Review-focus results

1. Corrupt reused source packet: rejected before fresh callback; targeted test passes.
2. Existing successful or failed response: reused, no repeated callback across restart; targeted test passes.
3. Reserved unanswered request: remains consumed, raises, records incomplete manifest; targeted test passes.
4. Three consecutive failures: replayed failures restore counter and stop across restart; targeted test passes.
5. Future/duplicate/overlap/mismatched budgets: rejected before callback; targeted test passes. Absolute494 API ceiling has the minor gap above; production CLI protects it.
6. Original fresh bytes across restart: payload changes reject; byte-only changes have the Important finding above.

## Declined to judge — explicitly considered and set aside

- Investment validity, profitability, alpha, account replay, candidate promotion, and 2026 holdout results: explicitly outside this source stage; no account or holdout work performed. A source admission does not establish these.
- Real historical arrival, server-authenticated historical date echo, queue position, market impact, counterfactual fills, and true minute-share capacity bounds: retained raw reconstructed packets and aggregate daily consistency cannot independently certify these. Existing false certification flags and a separately frozen execution stage are required.
- Full corporate-action and point-in-time fundamental certification: outside current source receipt/price-volume admission; no new certification is inferred.
- TCP packet/request counts, hidden SDK transport retries, server behavior and live failure recovery: no source network calls authorized in review. Only the logical493/max_attempts1 journal contract was assessed; the plan expressly limits this claim.
- Re-running the entire409-test suite: not done because this review explicitly prohibits account runs and the full suite includes broader account behavior. The reported full-suite pass is implementer evidence; reviewer independently ran all nine changed tests and both complete local source audits.
- Cryptographic defense against an actor replacing every frozen plan, code, packet, snapshot and all trusted hashes together: this is local audit provenance, not an external signed evidence store. Ordinary byte tampering/resume behavior was assessed and is not dismissed on this basis.
- Live durability under power loss and filesystem directory fsync semantics: not fault-injected; existing helper fsyncs written files, and missing or malformed reserved state fails closed. This review does not certify physical crash durability.
- Unchosen lower-priority cached packet corruption after the frozen inventory: selected839 bytes and all frozen manifest hashes are current-authenticated; the frozen inventory previously authenticated1238 relevant origins and recorded zero semantic conflicts. No new claim is made that every unselected duplicate was re-read by admission. This does not excuse any selected packet corruption.
- Future proposed v2 implementation: not present in reviewed HEAD; the design conditions above are not a passing implementation verdict.

## Assessment

Ready to merge/publish as a supported restart-safe capture implementation: WITH FIXES (one Important finding).

Actual supplied source-stage evidence: independently reproducible and internally consistent for the complete pre2026 reconstructed prefix. Preserve those frozen bytes and original hashes. Fix the supported restart entrypoint and its regression evidence before claiming its byte immutability guarantee; do not convert source admission into candidate promotion or objective completion.
