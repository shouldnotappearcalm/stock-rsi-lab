# Operating Corpus Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish complete source and latest-filing coverage for the operating-profitability hypothesis without ranks or returns.

**Architecture:** A metadata-only availability adapter consumes complete versioned source cases. A bounded immutable runner authenticates and parses all original caches, then emits48 cohort-complete snapshots. A separate stdlib checker verifies literal source cells and selection witnesses.

**Tech Stack:** Python3.11.15, Decimal, unittest, four foreground source workers, existing authenticated pypdf6.10.0 caches.

**Spec:** `docs/research/operating-corpus-source-design-2026-10-23.md`

## Global Constraints

- Exact394 issuers/1236 reports; all six2017-2021 reissues and failures retained.
- No new PDF decoding/network/price/2026 financial data/ratios/ranks/returns.
- Keep current operating contract and prior methods/outputs unchanged.
- Same24 explicit-session monthly transitions in2024/2025; OBSERVED/conditional reconstructed modes.
- All input/request hashes checked on every exit; source corruption fatal; summary atomic and failure evidence preserved.

## Review Focus

- Newer unsupported source or same-day conflicting PDFs must block older values.
- Old-year late reissue must not displace a more recent fiscal year.
- Future annual metadata/case payload must remain unread until visibility.
- Cache corruption, source/request mutation and summary persistence interruption must fail closed.
- Monetary evidence must match original consolidated row, unit, date and column; no parent or cross-edition substitution.

### Task 1: Metadata-only operating availability

**Files:** Create `src/stock_rsi/operating_availability.py`, `tests/test_operating_availability.py`.

**Interfaces:** Consumes documents, `case_reader(key)`, archived industry catalog and complete cohort. Produces `snapshot_availability(documents,case_reader,industry,cohort,as_of,*,mode=OBSERVED)->dict` with all issuer statuses/source pointers and no amounts.

- [ ] Write failing tests for observed/future isolation, publication/arrival boundaries, latest failed blocking, fiscal ordering, same-day ambiguity/identical-byte witnesses, source/clock corruption, cutoff and complete industry rows/no monetary exposure.
- [ ] Run `PYTHONPATH=src:. python -m unittest tests.test_operating_availability -v`; expected missing-module assertions.
- [ ] Implement the adapter using existing catalog/clock helpers and current report validation; no ratio helper calls.
- [ ] Run target tests and full suite; expected all pass, then commit with spec/plan.

### Task 2: Bounded complete-corpus runner and independent checker

**Files:** Create `scripts/inspect_operating_corpus_source.py`, `scripts/audit_operating_corpus_source.py`, `tests/test_operating_corpus_runner.py`, `tests/test_operating_corpus_audit.py`; create frozen request and derived source/coverage/audit results.

**Interfaces:** Runner produces `required_paths(base,root,membership)->dict`, `verify(...)->(request,paths)`, `inspect_one(base,document,normative_basis)->dict`, `run(base,root,membership,request_file,expected_sha,*,executor_factory,worker)->dict`. Checker produces `check_case(pages,document,case)->int`, `audit(base,root,membership,request_file,expected_sha)->dict` using stdlib only.

- [ ] Write failing runner tests for both cache locations, retained identity/schema failures, old GP value controls, corrupt cache fatal, complete latest coverage, immutable outputs, original interruptions/mutation and staged-summary failure. Write checker tests for original row/column/unit/scope and forged cell/selection rejection.
- [ ] Run both test files; expected missing-module assertions.
- [ ] Implement fixed corpus closure/worker/atomic terminal lifecycle and independent source/witness checks. Record all unsupported cases, never source-filter them.
- [ ] Run targeted tests and full suite; expected all pass. Obtain one independent production-code review, resolve Important findings with RED→GREEN regressions before source freeze.
- [ ] Bind exact documents, cohort, formations, all inputs/methods and no-value/rank/return scope; commit/push request/methods and verify remote freeze before actual execution.
- [ ] Run actual source inspection once in fresh output, then independent checker. Expected1236 case entries,48 complete394-row views, all observed annual counts zero, all supported raw cells/source witnesses checked, all inputs/outputs unchanged. Retain failures and stop admission if checks fail.
- [ ] Publish byte-identical summaries/checks and coverage/failure analysis; full suite and exact final three CI jobs must pass, then preserve active research worktree.

## Self-review

Both tasks use `operating_report` and statuses `OPERATING_CELLS_SUPPORTED_PENDING_SOURCE_QA`, `OPERATING_SOURCE_SCHEMA_UNSUPPORTED`, `COVER_IDENTITY_UNVERIFIED`. Task2 invokes exactly Task1's interface and never computes a source ratio. All five review-focus behaviors have tests. An unsupported corpus is a valid research finding, not objective completion.
