# Selective Tencent History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate captured pre2026 OHLCV against the frozen control before decoding the missing stock.

**Architecture:** Byte-slice JSON boundary, exact source projector/control gate, authenticated immutable runner and separate projector checker sharing only the slice walker.

**Tech Stack:** Python stdlib, Decimal, unittest; no installs/network/account.

**Spec:** `docs/research/low-operating-tencent-decode-design-2026-10-23.md`

## Global Constraints

- Keep full three-period goal and all43names/24targets/95%weights/costs fixed; preserve prior failures, no2026outcomes/account/return.
- Only explicit2023-12-29..2025-12-31sessions,1MiB/64depth limits, no whole body/row decode, opaque ignored values.
- Exact control OHLC/volume100, amount10000 independent exact diagnostic, no tolerance/filled state/arrival.
- Full input closure/buffer authentication, every written row retained, no target after control/context failure.

## Review Focus

- Poisoned ignored/extra/2026row values cannot reach a scalar decoder; malformed structures and ambiguous paths fail.
- Missing/duplicate/out-of-order dates or non-cent/nonfinite values cannot become admitted rows.
- One control price/volume mismatch or bound-input mutation prevents target value decoding.
- Optional metadata stays unknown/independently unadmitted; no price/amount conflation.
- Earlier-output mutation/native interruption preserves original evidence and completed prefix; checker never finishes failed target reads.

### Task 1: Selective source projection and actual controlled decode

**Files:** Create `src/stock_rsi/tencent_history.py`, `scripts/decode_low_operating_tencent_pre2026.py`, `scripts/audit_low_operating_tencent_pre2026.py`, `tests/test_low_operating_tencent_decode.py`; request/review/results/evidence.

**Interfaces:** `JsonSlices(body).path(tuple)->bytes`, `.items(array_bytes)->list[bytes]`; `decode(body,code,sessions,on_row=None)->list[dict]`; `compare(rows,raw)->dict`; runner `context(base,root)`, `authenticate(base,root,request,sha)`, `run(...)`; checker `audit(...)`.

- [ ] RED synthetic tests for ignored poison/future date, framing/path/duplicate/depth, schemas/units/control failure, authenticated target boundary and incremental failure/immutability; expected missing-feature failures.
- [ ] Implement selector/projector/runner/checker; targeted and full suite GREEN; commit.
- [ ] One fresh whole-change review, single RED/GREEN correction pass for Important/Critical, full suite; ledger all rulings/costs.
- [ ] Freeze new request/method/entire source closure, push and verify exact remote before actual decode.
- [ ] Decode once in fresh output, separate projector check and root full hash verification. Publish actual gates/coverage/failures, without new account/return claims.
- [ ] Native task-done/full suite, push/final3CIgreen, archive/remove own workflow folder; retain active full goal/worktree.

## Self-review

One coupled selective decode contract. Date-before-value, shared-selector audit limits and per-field control outcomes are explicit; no source success is redefined as investment success.
