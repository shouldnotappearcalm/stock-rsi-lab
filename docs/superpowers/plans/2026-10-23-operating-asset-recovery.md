# Operating Asset Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover coherent prior-year-end asset/income source records and complete coverage before the next frozen strategy experiment.

**Architecture:** A pure word-geometry mapper feeds a separately versioned source composer. A bounded full-corpus runner preserves legacy results and targets every339 original date failures. A separate checker verifies source positions, income cells and original monthly selection witnesses.

**Tech Stack:** stdlib/Decimal/unittest, existing operating grammar, Python3.12.14/pdfplumber0.11.9 for actual source reads.

**Spec:** `docs/research/operating-asset-recovery-design-2026-10-23.md`

## Global Constraints

- Original1236cases/394issuers/339target failures/six older reissues and all prior methods/outputs unchanged.
- No network, price,2026 financial values, factor ratio, ranking, return or broker action.
- Regulatory2021 version only; dates2021-06-28..2025-06-30; coordinates2/12/24pt bounds per spec.
- Exact first20 cached-page search; at most two non-overlapping two-page windows plus primary row (five/target,1695total); four processes/outstanding maximum.
- Full source hashes, same-edition income/assets, explicit observed clocks, all48 original metadata views; fresh immutable outputs and exit postchecks.

## Review Focus

- Wrong-year adjusted columns and percentage cells must never become prior assets.
- Parent/other-edition/foreign-unit evidence and coherently forged source records must fail.
- Future/unselected cases must remain unread by coverage augmentation.
- First worker/submit/persistence failure must preserve completed peers and original exception.
- Missing row/header, interrupted source reads, corrupt caches and changed inputs must retain failures and prevent completion.

### Task 1: Geometry, source report and metadata augmentation

**Files:** Create `src/stock_rsi/asset_geometry.py`, `src/stock_rsi/operating_source_bridge.py`, `tests/test_asset_geometry.py`, `tests/test_operating_source_bridge.py`.

**Interfaces:** `parse_summary_assets(pages,report_year,publication_day,source_sha256,primary,*,normative_basis)->dict`; `recover_source_record(document,text_pages,geometry_pages,primary_cell,*,normative_basis)->dict`; `augment_coverage(view,case_reader)->dict` as specified.

- [ ] Add real four-edition tests using `tests/fixtures/operating-asset-summary-real-word-geometry.json`: exact current/prior values, source-year/adjustment selection, all columns retained, and January1/unknown dates preserved; output contains no ratio/admission.
- [ ] Add mutations for swapped/missing year/adjustment headers, fake extra money/percent, duplicate words/pages, cross-page gaps/width/source mismatch, nonfinite/outside coordinates, foreign units, absent/changed regulatory basis and later publication, and primary source/amount mismatch. Reversed input word order must preserve output.
- [ ] Add synthetic complete signed income/report identity, missing R&D, forged report inputs/clocks, and full-view visible-only augmentation/future-trap tests. Do not claim synthetic income is real source evidence.
- [ ] Run `PYTHONPATH=src:. python -m unittest tests.test_asset_geometry tests.test_operating_source_bridge -v`; Expected: missing-module assertions.
- [ ] Implement pure mapper and source composer without changing old modules. Expected: target tests pass; run full suite, commit and task-done with the target command.

### Task 2: Frozen complete recovery, separate source checker and publication

**Files:** Create `scripts/recover_operating_assets.py`, `scripts/audit_operating_asset_recovery.py`, `tests/test_operating_asset_recovery.py`, `tests/test_operating_asset_recovery_audit.py`; create request/review/results/check evidence and research results note.

**Interfaces:** `candidate_pages(texts,year,primary_page)->list[int]`; `inspect_one(base,document,normative_basis)->dict`; `run(base,root,membership,request,expected_sha,*,executor_factory,worker)->dict`; checker `check_case(original_texts,geometry,document,original_case,new_case)->int`, `audit(...)->dict`.

- [ ] Write and run RED tests for exact page budgets/source selection, no source/income/price on excluded branches, all original cases/failed latest coverage, cache/authentication corruption, immutable outputs and original-error/peer-drain/postcheck lifecycle. Checker tests must reject rehashed amount/year/adjustment/unit/scope/identity forgeries and verify actual row evidence without importing new producer code.
- [ ] Implement bounded source runner, complete input closure and independent source/witness checker. Expected: targeted tests and full suite pass.
- [ ] Obtain one fresh whole-change code review before source freeze. Resolve Important/Critical findings with one RED→GREEN fix pass and green suite; record deferred claims/rulings.
- [ ] Bind all339 targets plus full1236 legacy corpus/48views, all methods/inputs and source budgets. Push and verify exact remote freeze before actual source extraction. Expected: source-only preflight passes and old artifacts/methods agree.
- [ ] Run once in fresh output, then frozen independent checker. Expected: all1236 cases retained, all339 attempts/unsupported states retained,48complete394-row views, all historical OBSERVED annual counts zero, all supported source cells and selected witnesses checked, input/output identities unchanged. Preserve failed run rather than expanding parser silently.
- [ ] Publish byte-identical summary/check plus full failures/coverage and limits. Verify full suite and three exact-final-head CI jobs; task-done, preserve research worktree, keep overall return goal active until independently proven.

## Self-review

Task1 returns source records and metadata-only case pointers consumed by Task2; canonical source page shape and normative basis are shared exactly. Every review-focus condition has an explicit mutation/lifecycle test. Recovery can fail legitimately; the return objective is not replaced by parser counts.
