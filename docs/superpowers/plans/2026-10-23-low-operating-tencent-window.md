# Tencent Date-Window Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quarantine earlier opaque rows and verify actual allowed-window quotes through the unchanged strict source gate.

**Architecture:** Date-only adapter + frozen projector/finalizer, fresh authenticated source experiment and separate old projector reconstruction with disclosed shared boundaries.

**Tech Stack:** Python stdlib/unittest, no installs/network/accounts.

**Spec:** `docs/research/low-operating-tencent-window-design-2026-10-23.md`

## Global Constraints

- Same43names/24targets/95%weights/costs and full three-period goal; preserve all prior failures/method bytes.
- Exact2023-12-29..2025-12-31/486sessions; earlier prefix date-only quarantine; future/offcalendar/duplicate/reverse fail before numeric decode.
- Keep row bytes verbatim, trace indices/date/hash/classification; ignored slots/current values opaque; no filled state or amount tolerance.
- Full previous proof closure plus methods/spec/plan/review; per-write/post-publication integrity and target boundary checks.

## Review Focus

- Poisoned earlier/current/extra values never reach scalar decoder; source ordering and schema errors stay failures.
- Prepared bytes/receipt cannot omit, reorder, alter or admit a future/offcalendar row.
- One control price/volume/input/evidence failure prevents target preparation/decoding.
- Native interruption preserves partial dates and durable numeric prefixes, markers and aggregates.
- Checker validates all extra receipt/prepared artifacts and completed prefixes without continuing failed numeric reads; shared-boundary limits explicit.

### Task 1: Date-only preparation and frozen actual window experiment

**Files:** Create `src/stock_rsi/tencent_window.py`, `scripts/run_low_operating_tencent_window_pre2026.py`, `tests/test_low_operating_tencent_window.py`; request/review/results/evidence.

**Interfaces:** `prepare(body,code,sessions)->(bytes,dict)`, `context(base,root)`, `authenticate(...)`, `run(...)`, `audit(...)`. Consumes unchanged selective producer `evaluate`, `persist`, `finish_source` and checker `project`, `verify_projection_artifacts`.

- [ ] RED tests for poison quarantine/byte provenance/date errors, unchanged strict projection/control failure, late mutation and native failure artifact reconstruction.
- [ ] Implement adapter/orchestration/check; targeted/full suite GREEN, commit.
- [ ] One fresh whole-change review; single tested correction pass, full suite; ledger all rulings/costs/deferred minors.
- [ ] Freeze/push/verify exact remote before actual date/value scan; run once fresh and separately reconstruct all identities/preparation/components.
- [ ] Publish real control/target coverage or retained failure; root full hashes; native task-done/full suite, final push/3CIgreen, archive own workflow; full goal active unless actually achieved.

## Self-review

One coupled source preparation contract. Earlier quarantine preserves the original investment window; unchanged strict projector catches any admitted-date mistake. Shared boundaries and source-only admission limits are explicit.
