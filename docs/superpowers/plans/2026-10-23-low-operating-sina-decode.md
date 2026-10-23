# Native Sina Component Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test native Sina exact historical price/volume components without reading outside-window quote values or changing the strategy.

**Architecture:** Date-only raw-row selector and exact scalar projector; a new derivative of the frozen Yahoo runner, shared-projector audit and unchanged comparator/finalizer.

**Tech Stack:** Python3.11+ stdlib, existing installed runtime only.

**Spec:** `docs/research/low-operating-sina-decode-design-2026-10-23.md`

## Global Constraints

- Same43names/24targets/95%weights/costs; full2024>0/2025>0/2026Jan–Oct>=10% remains unachieved; no2026outcome tuning.
- All date tokens first, both outside prefixes/tails quote-opaque; admitted486explicit sessions only; exact cent OHLC/integer-share volume with no tolerance/fill/adjustment.
- Preserve old methods/source failures; authenticate full original graph/current methods and every published artifact.
- Exact complete control before target, durable prefixes and native diagnostics on failure; shared decoder audit disclosed; no account/return admission.

## Review Focus

- Outside-window malformed quote values/extra metadata never reach scalar conversion; wrong dates, ordering, duplicates and offcalendar inside rows fail first.
- Numeric exponent/tail/null/fractional-volume defects cannot be hidden by conversion or precision loss.
- Corrupt/missing control evidence or mutated input/output at marker/load/publication prevents target projection.
- Error stage/index/invocation/aggregate/closure combinations must be reachable; incomplete numeric prefixes are not finished during audit.
- No new future data, wrapper defaults, network or account/return claim from passing component checks.

### Task 1: Selective native source projection and actual immutable probe

**Files:** Create `src/stock_rsi/sina_history.py`, `scripts/decode_low_operating_sina_pre2026.py`, `tests/test_low_operating_sina_decode.py`, request/review/results/checks.

**Interfaces:** `select(body:bytes,code:str,sessions:list)->list[(source_index,day,raw_row)]`, `price(token:bytes)->str`, `decode(body,code,sessions,on_row=None,prefix_rows=None)->list`. Runner exposes the existing Yahoo script's context/authenticate/evaluate/run/verify_artifacts/audit signatures, with Sina identities and date-only aggregate counts.

- [ ] RED tests: poison both tails, all date pass before quotes, strict scalar/identity/date errors, exact control gate, run/shared audit, marker/load mutation, durable native prefixes, control evidence and impossible error states. Run targeted unittest: Expected missing-feature failures.
- [ ] Implement projector and new derivative runner; targeted and full suite GREEN; metadata-only complete context preflight, commit. Expected: no real Sina date/quote scans.
- [ ] One fresh whole-change review; single tested Important/Critical correction pass and full suite; record rulings/costs/minors; no rereview.
- [ ] Freeze/push/verify exact remote; run once fresh, separate shared-projector audit and root full hashes; publish actual control/target coverage or retained failure. Expected: zero account/return/goal admission.
- [ ] Native task-done/full suite; final push/exact remote/3CIgreen; archive own workflow; full investment goal remains active unless actually proved.

## Self-review

One coupled source contract. The inherited runner's aggregate-count branch must use selected native rows, not Yahoo timestamps. No other task interface conflicts.
