# Operating Profitability Development Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run one frozen operating-profitability candidate on2024/2025 and independently prove its source/target/account evidence before any2026 continuation.

**Architecture:** A visibility-first approved-source consumer feeds exact-ratio monthly targets; a frozen runner reuses the unchanged prior-close account engine. A separately implemented checker verifies all source admissions/ranks plus native account and order intentions.

**Tech Stack:** stdlib/Fraction/unittest; existing Python3.11.15/Qlib0.9.8/numpy2.4.6/pandas2.2.3 runtime.

**Spec:** `docs/research/operating-profitability-development-design-2026-10-23.md`

## Global Constraints

- Preserve all consumed source/account/provider methods and old artifacts;394cohort/1236source editions/24formations.
- Single primary high operating ratio decile,95% target, same-eligibility equal/bottom controls never promotable; minimum100names and original fiscal freshness rule.
- CNY1,000,000 continuous2024-01-02..2025-12-31; prior-close decisions/next open,5/15bps base plus20/40bps stress,CNY5minimum.
- Default OBSERVED excludes future/captured-late payload before reader/hash; development explicitly reconstructed; approved source IDs and same-PDF dated denominator required.
- No2026 values/network/broker/background; immutable fresh outputs, all-exit postchecks and original errors.
- Primary40bps development gate:2024/2025 each>0,exposure>=90%,zero unverified marks; no raw/investment/goal claims.

## Review Focus

- Forged/rehashed records and missing asset evidence must fail even when numbers look plausible.
- Future/unselected records, failed latest sources and controls must not become ranking inputs or promoted candidates.
- Negative administrative/profit values and separately expensed R&D must preserve exact intended arithmetic.
- Initial reads, source/profile failures and final-summary/postcheck persistence failures must retain prefixes and prevent completed summaries.
- Prior-close targets must link to actual ledger inventory/equity and submitted orders; account conservation alone cannot prove strategy execution.

### Task 1: Approved source ratios and monthly target construction

**Files:** Create `src/stock_rsi/operating_factor.py`, `src/stock_rsi/operating_monthly.py`, `tests/test_operating_factor.py`, `tests/test_operating_monthly.py`.

**Interfaces:** `source_observation(document,case_reader,legacy_reader,approved_ids,as_of,*,mode=OBSERVED)->dict|None`; `build_targets(snapshot,memberships,cohort,source_views,documents,case_reader,legacy_reader,approved_ids,start=START,end=END,*,on_formation=None)->(targets,receipts)`.

- [ ] Add synthetic legacy/new same-income signed arithmetic and R&D tests, current-period-only exact ratios, default observed/future-reader trap, approved-ID/hash/source/clock/scope/date/unit/nonnull-asset forgeries.
- [ ] Add110-name synthetic target tests: exact top/bottom/equal weights, all exclusions and no older fallback, ties/negative values, future views/payloads ignored, finite quotes, minimum100 and persisted prefix on a later failure.
- [ ] Run `PYTHONPATH=src:. python -m unittest tests.test_operating_factor tests.test_operating_monthly -v`; expect missing-module RED.
- [ ] Implement visibility-first approved source consumer and exact monthly selection; target/full suite GREEN; commit and native task-done with targeted command.

### Task 2: Frozen run, independent source/intent/account audit and publication

**Files:** Create `scripts/run_qlib_operating_pre2026.py`, `scripts/audit_operating_pre2026.py`, `tests/test_operating_development.py`, `tests/test_operating_development_audit.py`; request/review/results/coverage/check artifacts and research results note.

**Interfaces:** runner `required_paths(base,root,membership)`, `verify(...)`, `form_targets(base,req,out)`, `run(...,form_targets=...,simulation=...)`; checker `source_score(document,case,legacy_record,approved_id,as_of)`, `audit_formations(...)`, `audit_intents(...)`, `audit(...)`.

- [ ] RED tests for full frozen closures/scope, positive primary and losing primary with profitable controls, all six outputs/finite metrics, fresh-only and partial target/profile/source/summary/postcheck lifecycle.
- [ ] RED checker tests for independent exact signed ratios, rehashed identity/unit/date/flag forgeries and normalized account/target/intent substitutions; exercise real checker behavior, not text matching.
- [ ] Implement runner and separate checker, reusing old immutable quote-engine and independently implemented native account checker; all target/full tests GREEN.
- [ ] One fresh code reviewer before real ratios/returns; one RED-to-GREEN correction pass for Important/Critical, full suite, record rulings/deferred claims, no rereview.
- [ ] Build complete source/engine input and method/runtime/request bindings, source-only preflight; push and verify exact remote freeze before new financial ratios/price reads.
- [ ] Run once in fresh output, then frozen separate checker; retain failure/rejection without threshold/direction/source changes or2026 reads. Publish byte-identical proof/results/all coverage; full suite and three exact-final-head CI jobs pass; task-done and only own workflow folder cleanup, preserve research worktree and active return goal.

## Self-review

Task1 consumes the frozen source registry and metadata; Task2 uses the identical signatures and payload-free approved IDs. Every review-focus case has a source/formation/lifecycle/intent regression. Published normalized returns are a conditional development screen, not the raw-share/full2026 gate.
