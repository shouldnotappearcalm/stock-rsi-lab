# Low Operating HTTP and Tax Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the frozen candidate's missing raw-bar source and alternative net-dividend text at source level, preserving all failed attempts and account limits.

**Architecture:** Literal-tax parser plus narrow two-resource HTTP collector over authenticated failed-capture context; separate checker imports no new producer. Source sub-results stay distinct and never promote a strategy/account.

**Tech Stack:** Existing Python stdlib/unittest; no install/SDK/network retry.

**Spec:** `docs/research/low-operating-http-tax-source-design-2026-10-23.md`

## Global Constraints

- Same adaptive low-OP43names/24targets/95%weights; no strategy/account/evaluator change or2026values/returns/broker/background.
- Preserve5b02755and all209old input bindings/42captured packets/failed SDK/checker artifacts; source window2023-12-29..2025-12-31,486explicit sessions.
- Preserve literal after-tax options/empty unknown and original row hashes; no chosen net/rate/zero or tax admission.
- Exactly2GETresources(SZ002326,SH600118control),one attempt each,20s,1MiBcap, no redirects/fallback/retry/resume; fqt0/klt101/explicit endpoints/dates/fields frozen.
- All4OHLC exact,volume100shares/lot exact,amount tolerance0.01yuan; mismatch is reported failure, not tuned after observing values.
- No fake isST/preclose/arrival/action state; raw source support and full investment acceptance remain separate.

## Review Focus

- Alternate tax text must remain literal/unselected; copied schema view must not modify original input or hide other invalid fields.
- Server response outside requested dates, extra quote fields or missing/wrong rows must not enter accepted historical bar projection.
- One failing resource cannot widen HTTP identity/budget, erase raw failures or make the other resource's status imply full success.
- Control source disagreements/units must be exposed and prevent corroboration; cannot infer corporate facts from price differences.
- Late input/output changes or uncommitted finalization must prevent completion; checker must rederive source facts without importing new producer.

### Task 1: Frozen two-resource source diagnostic and literal-tax bridge

**Files:** Create `src/stock_rsi/vendor_dividend_tax_text.py`, `scripts/capture_low_operating_http_pre2026.py`, `scripts/audit_low_operating_http_pre2026.py`, `tests/test_low_operating_http_tax_sources.py`; public request/review/terminal/check/results artifacts and research results note.

**Interfaces:** tax `parse_net_cash(text,gross)->dict`; producer `parse_bars(body,code,sessions)->list`, `control_check(bars,original)->dict`, `context(base,root)->(dict,list,dict)`, `authenticate(base,root,request,sha)->(dict,dict)`, `execute(req,auth,out,opener)->dict`; checker `audit(base,root,raw,request,sha)->dict`.

- [ ] RED behavior tests for all literal-tax/HTTP/control/persistence boundaries in spec, real expected failures before implementation.
- [ ] Implement parser, collector and separate checker; targeted/full suite GREEN; commit.
- [ ] One fresh whole-change reviewer; one RED/GREEN correction pass for Important/Critical, full suite; record every deferred claim/cost and no rereview.
- [ ] Freeze exact resources/method/context/request, source preflight and push; verify remote HEAD before actual HTTP. No source/strategy parameter changes after freeze.
- [ ] Execute one fresh bounded foreground capture; separate frozen checker independently reconstructs both HTTP outcomes and42tax-risk views; preserve every failure without retry.
- [ ] Publish actual outcome/remaining source/account conditions, full tests and three exact-head CI jobs; native task-done, archive/remove own workflow folder, preserve worktree and active full return goal.

## Self-review

One coupled source-contract deliverable: tax parser and HTTP projection feed the same source-level terminal/checker; exact schemas/identities and all review-focus failures have behavior tests. No accepted price or tax view stands in for a physical account.
