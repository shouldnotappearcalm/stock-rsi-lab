# Cash Accrual Wrapped Caption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task-by-task.

**Goal:** Recover source formats with wrapped total-net-profit captions without altering financial facts or investment rules.
**Architecture:** ImmutableV1grammar/output lineage; pureV2bounded caption adapter and separately frozen whole-corpus derivative. Preserve old227successful reports exactly.
**Tech Stack:** ExistingPython3.11+,stdlib,existing PDFpage caches/render runtime; no installs.
**Spec:** `docs/research/cash-accrual-wrapped-label-design-2026-10-23.md`

## Global Constraints

- Full2024>0/2025>0/2026Jan–Oct>=10% goal active, no2026selection/newvalues/ranks/accounts/returns; no brokers/background/install.
- Same1236original editions/394issuers/publication<=2025-12-31; all old failures/reissues retained; new output only.
- Captionwhitespace-only,12same-page lines max, original monetary tail unchanged, exact2fiscal cells/explicit note grammar, original source scope/header/unit/date checks.
-227V1reports/digests preserved identically;4workerbatches/4sourcefilehashes,drainpeers/nativefailure retained,fullhashes before/after/publication.
- Native implementation, one fresh final reviewer,one testedImportant/Criticalfixpass,no rereview;ledgerallrulings/costs/minors.

## Review Focus

- Digit/sign/decimal whitespace must not be normalized with caption characters; Task1tail fixtures reject financial-token merging.
- Parent/continuing/attributable/subtotal or page/header/duplicate/third-cell substitutions cannot rescue a row;Task1source witness tests.
- Mixed/source contract or raw-caption provenance tampering must fail even after digest recomputation;Task1reports/Task2worker acceptance.
- Original227report preservation,protectedassetchecks and complete oldcase reproduction cannot be bypassed by ordinary unsupported status;Task2integrity tests.
- Worker/native/setup/output/input/publication errors retain prefixes,drain submitted peers and never claim source/economic completion;Task2orchestration tests.

### Task 1: Bounded caption-only grammar extension and real rows

**Files:** Create `src/stock_rsi/annual_cash_accruals_v2.py`, `tests/test_annual_cash_accruals_v2.py`, `tests/fixtures/annual-cash-accrual-wrapped-real-rows.json`.
**Interfaces:** `net_profit_cells(table,year)->dated_cells`; `parse_report(pages,year,normative_basis=None)->parsed`; `make_report(document,parsed)->report`; `visible_report(document,as_of,loader,mode)->report|None`; `verify_source_tables(parsed,pages,year,normative_basis=None)->None`.
- [ ] Write failing tests for4real/8handcheckedvalues,2/8line syntheticrows,exact unmodifiedtail,negativevalues,12lineboundary/crosspage/duplicates/thirdcell/header/child substitutes,byte-identicalV1preservation,provenance/contracts/lazy clocks.
- [ ] Run `PYTHONPATH=src:. RP -m unittest tests.test_annual_cash_accruals_v2 -v`:missingfeatureRED.
- [ ] Implement new adapter only; targeted/fullsuiteGREEN;commit;native taskdone.

### Task 2: Source-bound full-corpus continuation

**Files:** Create `scripts/inspect_cash_accrual_wrapped_corpus.py`, `tests/test_cash_accrual_wrapped_corpus.py`, request/review/results/root evidence.
**Interfaces:** `inspect_one(base,doc,normative_basis,known)->case`; `bindings/verify`; `execute(req,known,out,base,worker,executor_factory)->terminal`; sourceCLIasV1.
- [ ] Write failing tests for actual-buffer/oldcase mismatch,old supported preservation and unsupported/cover/metadata/protectedassetnativeerrors,V2reportacceptance,completebatch/draining/setup/nativefailure/input-output-terminalmutation.
- [ ] Implement derivative with source-only gates; targeted/fullsuiteGREEN;commit synthetic only.
- [ ] One fresh final reviewer;one testedImportant/Criticalcorrectionpass/fullsuite;allrulings/costs/deferredminors, no rereview.
- [ ] Freeze full closure and explicitcase/workerbudget;push/exactremoteverify; actualall1236oncefresh;rootrehash/cell/preservation/sourcewitness audit; publish actualcoverage/failures.
- [ ] Native taskdone/fullsuite; finalpush/exactremote/3CIgreen;archiveonly ownworkspace;fullobjective remains active until allthreeperiodsactuallyverified.

## Self-review

Only source formatting changes. Task1defines dual report contracts;Task2reproduces oldcases before extending failures and never promotes incomplete monetary data. Review focus owns tail/scope/lineage/failure boundaries. Source coverage cannot substitute for investment admission or returns.

## 2026-10-27 continuation ruling

The original fresh reviewer was interrupted without a final verdict. Complete the source audit inline, disclose its same-author limitation, correct the two reproduced Important defects in one pass, and retain all failures. Do not claim a completed independent review or spawn a replacement reviewer. All source freeze/preservation and investment restrictions remain unchanged.
