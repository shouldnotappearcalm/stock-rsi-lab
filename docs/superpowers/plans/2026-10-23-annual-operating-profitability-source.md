# Annual Operating Profitability Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and source-verify an explicitly defined Chinese operating-profitability measure before cohort research.

**Architecture:** A separate source-only parser/record/view module reuses unchanged annual table grammar. A frozen generator validates both original PDFs and manual raw-cell evidence, writes immutable outputs and checks all consumed inputs on every exit.

**Tech Stack:** Python3.11+, Decimal, unittest, existing annual v7 grammar, pypdf6.10.0.

**Spec:** `docs/research/annual-operating-profitability-source-design-2026-10-23.md`

## Global Constraints

- Contract `CN_OP_EX_RND_SAME_EDITION_LAGGED_ASSETS_V1`; no cash-profitability/Compustat replication claim.
- Current numerator revenue-cost_of_sales-selling_expenses-administrative_expenses; same-PDF priorDecember31 assets; separately reported R&D is evidence only.
- No2026 financial/market values, ranks or portfolio returns; preserve all failures, unsupported sources and prior parsers.
- Exact signed CNY amounts,60-digit arithmetic; no zero fill or clipping; observed historical views stay empty.
- Reuse the existing isolated `pead` worktree and direct inline execution/push authorization.

## Review Focus

- R&D separately reported: altering its amount must not alter this numerator.
- Generic or January1 opening balance: never invent the laggedDecember31 denominator.
- Negative expense reversal or negative operating profit: preserve the source sign.
- Future/malformed payload: do not access before visibility; reject after visible.
- Interruption plus source/request mutation: retain the original exception and postcheck failure evidence; no completed summary.

### Task 1: Annual operating source contract

**Files:** Create `src/stock_rsi/annual_operating.py`; test `tests/test_annual_operating.py`.

**Interfaces:** Consumes existing v7 financial context, currency/header grammar and exact-money normalization. Produces `parse_report(pages, report_year, *, normative_basis=None) -> dict`, `make_report(instrument, report_year, publication_day, observed_at, document_sha256, announcement_id, parsed) -> dict`, `snapshot_reports(reports, as_of, *, mode=OBSERVED) -> dict`.

- [ ] Write failing tests: literal25/100=.25 rather than25/200; no comparative ratio; R&D invariance; negative expense gives35/100=.35; negative profit retained;万元 normalization; missing/duplicate/ambiguous/foreign-currency tables rejected; generic/January1 denominator rejected; cell/header/scope mutation rejected; actual arrival/publication-day-end boundaries; future payload isolation; independent editions and same-day conflicts.
- [ ] Run `PYTHONPATH=src:. python -m unittest tests.test_annual_operating -v`; expected assertion failures because the source module is absent.
- [ ] Implement the three interfaces in the separate module, with exact evidence validation and no strategy APIs.
- [ ] Run the target file and full unittest suite; expected all pass with no new skips.
- [ ] Commit module/tests/design/plan.

### Task 2: Frozen two-document source fixture and actual execution

**Files:** Create `scripts/build_operating_profitability_source_fixture.py`, `tests/test_operating_profitability_source_fixture.py`, `experiments/qlib/operating-profitability-source-review.json`, `experiments/qlib/operating-profitability-source-request.json`; after execution create `tests/fixtures/annual-operating-real-row-vintages.json` and the source results note/summary.

**Interfaces:** Consumes Task1's three interfaces and original capture/manual page evidence. Produces `required_paths(base,root) -> dict`, `verify(base,root,request_file,expected_sha) -> tuple`, `generate(base,root,request_file,expected_sha,out) -> dict` and a CLI accepting `--source-root --request --expected-request-sha256 --output-dir`.

- [ ] Write failing behavior tests for changed request/source bytes, excluded input, future/rank/return scope escalation, overwrite refusal and interrupted PDF read with mutated inputs/request.
- [ ] Run `PYTHONPATH=src:. python -m unittest tests.test_operating_profitability_source_fixture -v`; expected assertions because builder is absent.
- [ ] Implement fixed-input generator with preflight validation, exact raw-cell/page-text checks, both snapshot modes, original-error/postcheck persistence and no rank/return imports.
- [ ] Run target tests and full suite; expected all pass. Record independent review findings/fixes before source freeze.
- [ ] Commit/push request, raw-cell review and methods; verify remote head equals the freeze before executing.
- [ ] Execute generator once in a fresh output directory; expected two filing records, empty historical OBSERVED views, unchanged earlier snapshot with a future report present, all inputs unchanged, no strategy admission.
- [ ] Add versioned exact source-row CI regression, run it and full suite, independently recompute the two actual current-year numerators/lagged ratios from reviewed raw literals, verify output/input hashes, publish source summary/results and push. Expected latest three CI jobs succeed.

## Self-review

Both tasks preserve the same report/record/view contract. Task2 must not reuse
the old GP denominator or its4-observation output shape. The current-only ratio
requirement and2-report shape are deliberate. All five review-focus cases have
behavior tests assigned above. Source admission remains separate from cohort
coverage and the investment objective.
