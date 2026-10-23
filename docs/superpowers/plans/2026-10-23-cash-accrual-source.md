# Cash Accrual Original Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task-by-task.

**Goal:** Materialize complete original cash-accrual financial source cases for the next registered economic hypothesis, without computing returns.
**Architecture:** New pure source parser/report/lazy visibility adapter plus separate four-worker authenticated cohort runner. Immutable existing grammar/account/evaluators remain unchanged.
**Tech Stack:** Existing Python3.11+/stdlib and authenticated pypdf6.10.0page caches; no installs.
**Spec:** `docs/research/cash-accrual-source-design-2026-10-23.md`

## Global Constraints

- Full2024>0/2025>0/2026Jan–Oct>=10% objective active; no2026selection or new values, no brokers/background.
-1236original editions/394issuers, publication<=2025-12-31, existing original PDF/page-cache/cover identities; retain all failures/reissues.
- New source stage only, no ratios/ranks/targets/accounts/returns; missing source fields never zero filled or substituted.
- Current/prior signed consolidated NI and CFO; explicit same-edition positive current/priorDecember31assets; explicit units/currency and physical source evidence.
-4workers/batch, drain every submitted peer before error, fresh output/no overwrite; authenticate all intended input/output bytes during publication.
- Native implementation, one fresh final reviewer, one testedImportant/Critical correction pass, no rereview; record everyruling/cost/minordeferred.

## Review Focus

- Parent/summary/attributable-profit or multiple table/row substitutes must fail even when numbers look plausible; Task1pins source scope.
- Header/row/unit/period provenance tampering must fail at report validation; Task1pins source literals and coherent columns.
- Future/late report callbacks must be zero before public/arrival clock;Task1pins both modes.
- Worker publication/case metadata and prior asset disagreements must fail as native integrity errors, not unsupported cells;Task2pins all paths.
- Batch peer failures/input/output mutation must retain complete source-only failure evidence and never claim complete/no ratios/ranks/account;Task2pins orchestration.

### Task 1: Source cells and lazy report contract

**Files:** Create `src/stock_rsi/annual_cash_accruals.py`, `tests/test_annual_cash_accruals.py`.
**Interfaces:** `parse_report(pages,report_year,normative_basis=None)->parsed`; `make_report(document,parsed)->report`; `visible_report(document,as_of,loader,mode)->report|None`; `metadata(document)->(year,public,observed)`; `parse_asset_cells(pages,year,normative_basis=None)->dated_cells`; `verify_source_tables(parsed,pages,year,normative_basis=None)->None`.
- [ ] Write behavior tests for signed current/priorNI/CFO/assets, CNY/万元, missing/parent/duplicate/extra cells, wrong comparative dates/currency, source/hash/column tampering and lazy aware clocks.
- [ ] Run `PYTHONPATH=src:. RP -m unittest tests.test_annual_cash_accruals -v`: missing feature RED.
- [ ] Implement bounded grammar reuse, evidence validation/digest and visibility before loader. Run targeted/fullsuite GREEN, commit.

### Task 2: Whole-corpus authenticated inspection and actual source yield

**Files:** Create `scripts/inspect_cash_accrual_corpus.py`, `tests/test_cash_accrual_corpus.py`, request/review/results/root evidence.
**Interfaces:** `inspect_one(base,document,normative_basis,known)->case`; `verify(base,root,membership,request,expected)->(request,known)`; `execute(request,known,out,worker,executor_factory)->terminal`; CLI`--source-root/--membership-file/--request/--expected-request-sha256`.
- [ ] Write failing tests for authenticated actual page buffers/source/cover, old asset-cell parity, complete batches/draining, native errors and input/output/terminal mutations.
- [ ] Implement source-bound runner with source-only output schema; targeted/fullsuite GREEN, commit synthetic only.
- [ ] One fresh whole-change reviewer; one correction pass,RED→GREEN forImportant/Critical; fullsuite; everyruling/cost/deferredminor ledger. No rereview.
- [ ] Freeze fullsource graph/currentmethods/review/docs; push/exactremoteverify; run all1236oncefresh; separately rehash/reconcile cases and source cells; publish coverage/failures honestly.
- [ ] Native task-done/fullsuite; publicpush/exactremote/3CIgreen; archive only own plan workspace. Fullgoal active unless allthreeperiodsactuallyverified.

## Self-review

One source contract feeds one materializer. No account components or old producer files change. The new candidate formula is research registration, not a computed score or investment claim. Both units test visibility and integrity boundaries before actual financial extraction.
