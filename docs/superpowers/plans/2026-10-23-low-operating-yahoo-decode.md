# Selective Yahoo Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test the frozen Yahoo pre2026 price/volume source without reading current metadata or changing the strategy.

**Architecture:** Selective scalar projector, unchanged exact control comparison and immutable finalizer, shared-projector artifact audit.

**Tech Stack:** Python3.11+ stdlib, installed runtimes only.

**Spec:** `docs/research/low-operating-yahoo-decode-design-2026-10-23.md`

## Global Constraints

- Same43names/24targets/95%weights/costs;2024>0,2025>0,2026Jan–Oct>=10% remains unachieved; no2026values/outcome tuning.
- Entire timestamp array checked first; exact cents or unique native-f32 cent cell; exact integer shares, no tolerance/fill/adjustment.
- Full original opaque proof closure + current method/spec/plan/review; target only after verified complete control and immutable marker/buffer checks.
- Shared projector explicitly disclosed; no account/arrival/state/action/tax/return admission.

## Review Focus

- Future/current/adjclose/event values never reach scalar decoder; mismatched arrays or timestamps fail before any quote scalar.
- Decimal tails cannot disappear in float conversion; null/negative/nonfinite/ambiguous prices and fractional volume fail.
- Corrupt control rows/aggregate/summary and late input/output mutations prevent all target reads.
- Catchable row/load/persistence errors preserve reconciled durable prefixes; audit does not finish failed numeric reads.
- Error traces cannot bypass marker/count/aggregate/invocation/closure checks; original methods and source identities stay fixed.

### Task 1: Selective projector, frozen runner and artifact audit

**Files:** Create `src/stock_rsi/yahoo_history.py`, `scripts/decode_low_operating_yahoo_pre2026.py`, `tests/test_low_operating_yahoo_decode.py`, request/review/results/checks.

**Interfaces:** `price(token:bytes)->str`, `decode(body:bytes,code:str,sessions:list,on_row=None,prefix_rows=None)->list`; `evaluate(control_body,target_loader,sessions,original,on_row=None,on_report=None,before_target=None)`; `run(...)`, `audit(...)`. Reuse old JsonSlices/cell/control/finalizer; no source mutation.

- [ ] Write tests for poison metadata/future timestamps, raw tokens/native f32 cents, malformed values/arrays/identity, exact control failure, durable failure prefixes, target-boundary mutations and audit corruption. Run targeted unittest: Expected missing-feature RED.
- [ ] Implement interfaces and authentication/CLI. Targeted tests GREEN, full suite GREEN; commit. Expected: no actual Yahoo scans.
- [ ] One fresh whole-change review; one Important/Critical RED→GREEN correction pass, full suite; ledger rulings/costs/minors. No rereview.
- [ ] Freeze/push/verify exact remote; run once in fresh output, audit separately, rehash full closure and publish actual coverage or failure. Expected: no return/account claim regardless of source outcome.
- [ ] Native task-done/full suite; push final exact head/3CIgreen; archive own workflow. Full investment goal active unless all three real criteria proved.

## Self-review

One coupled source contract, no independent task interface conflicts. Source-only progress cannot prove the broader investment goal.
