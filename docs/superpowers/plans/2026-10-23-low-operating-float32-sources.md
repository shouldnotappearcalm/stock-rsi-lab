# Low Operating Float32 Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test one frozen exact-interval local price reconstruction against all42raw controls before recovering the missing stock's conditional quotes.

**Architecture:** Exact rational32bit bounds plus authenticated capped-binary runner; separately frozen bit-derived checker imports no new producer/math module. No strategy/account changes or new network data.

**Tech Stack:** Python stdlib,Fraction,struct,unittest; no installs.

**Spec:** `docs/research/low-operating-float32-source-design-2026-10-23.md`

## Global Constraints

- Same low-OP43names/24targets/95%weights/costs; preserve all failed SDK/HTTP artifacts and63literal tax alternatives. No account/ROI/new2026data/broker/background.
- Physically capped provider ends2025-12-31, source window2023-12-29..2025-12-31/all486sessions. Bind full preceding context plus original operating request/provider hashes.
- Exact binary32midpoint cells, fixed relative2^-40normalization guard, exactly one positive cent tick; no nearest-cent fallback or widened guard.
- All42raw controls/all20089rows counted, all trading OHLC includingST validated; nontrading source rows excluded explicitly and never filled. Any control price failure prevents SZ002326float decoding.
- Only volume scales1and100tested against every trading control row; unique scale only, conservative floor(lower bound), no invented exact volume/ST/preclose/amount/actions/PIT.
- Source-only conditional result never implies account or investment qualification; preserve errors and immutable fresh output.

## Review Focus

- Float32cells/ties/subnormals/zero/nonfinite/large ambiguous cent intervals must not become guessed prices or optimistic volumes.
- Incomplete/forged original/provider binding closure, bad headers/extents or a calendar containing2026must fail before feature decoding.
- Every trading control field/issuer must contribute to the gate; one failure prevents missing-code reads, including cached callbacks.
- Volume units and partial target coverage remain separate from price success; no source state/actions are inferred from factors.
- Late input/output changes and native exceptions must prevent completion/preserve evidence; independent checker must reconstruct every result from original bits.

### Task 1: Exact interval source probe, full controls and separate reconstruction

**Files:** Create `src/stock_rsi/float32_quote_bounds.py`, `scripts/recover_low_operating_quotes_pre2026.py`, `scripts/audit_low_operating_quote_recovery_pre2026.py`, `tests/test_low_operating_quote_recovery.py`; public request/review/control/projection/check/result artifacts and results note.

**Interfaces:** bounds `cell(value,allow_zero=False)->(Fraction,Fraction)`, `cent_price(value,factor)->dict`, `volume_interval(value,factor,scale)->(Fraction,Fraction)`; runner `read32(path,index,calendar_length)->float|None`, `controls(packets,sessions,get)->dict`, `project(sessions,get,scale)->list`, `context(base,root)->(dict,list,dict)`, `run(base,root,request,sha)->dict`; checker `audit(base,root,out,request,sha)->dict`.

- [ ] RED behavior tests for exact/empty/ambiguous cent cells, invalid/subnormal inputs and conservative volume; bounded reader/future tails; all-control gating/no missing-code reads, unit ambiguity, immutable persistence.
- [ ] Implement pure bounds/runner/separate checker; targeted/full suite GREEN, commit.
- [ ] One fresh whole-change reviewer; one RED/GREEN correction pass for Important/Critical, green full suite, ledger all deferred behaviors/costs; no rereview.
- [ ] Authenticate original capped-provider/source bindings, freeze request/methods/rules before first actual value comparison, push/verify exact remote HEAD.
- [ ] Run once in fresh low-operating-f32-source-recovery-v1-20261023; separate checker reconstructs all control/unit/projection results and before/after identities. Preserve any failure without new source/precision/rule changes.
- [ ] Publish actual conditional source result/remaining account conditions, full tests and exact-head3CIjobs; native task-done, archive/remove own workflow folder, retain goal/worktree.

## Self-review

One coupled reconstruction contract. Exact bound outputs and control counters feed runner/checker consistently. Every review focus has synthetic behavior coverage; quote recovery is a necessary source step rather than a smaller definition of the return goal.
