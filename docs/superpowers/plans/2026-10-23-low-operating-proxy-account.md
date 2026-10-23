# Low-OP Amendment-Aware Daily-Proxy Account Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Run the frozen low-OP43-name continuous2024/2025account with correct known amendment visibility and verified ordinary/STdaily bands.
**Architecture:** Pure lazy amendment adapter; separately versioned replay/helper/runner; existing source compiler, broker, allocator, account and finalizer unchanged.
**Tech Stack:** InstalledPython3.11+/stdlib; existing numerical/PDFtest runtime only.
**Spec:** `docs/research/low-operating-proxy-account-design-2026-10-23.md`

## Global Constraints

-2024>0/2025>0/2026Jan–Oct>=10% unchanged/unachieved; no2026outcome selection, no brokers/background/install. Oldmethods/sourcefailures immutable.
-Explicit486sessions,24targets,43codes,95%,1mcapital;5/15bpsbase/min5 plus20/40bps; flat20%dividendreserve is stress, notFIFOtax.
-Lazy source visibility before monetarycallbacks; sourcefix must reproduce originaltargetweights or stop; actualcasebothcosts before anyROI.
-Conditional joined-source states and daily execution disclosed; no source/account/return claim from green tests.

## Review Focus

-Future amendmentpayload poisoned: zero callback before public/capturedclock; wrongbasehash/period/unit/component/proofdigest never alters score.
-Reranking and normalized dictionary equality cannot silently authorize changed frozenweights or ignore modified originalselectionreceipts.
-Warningdate/code/permission/cumulative eligibleBUY, centrounding, suspension, orderexpiry/T+1/100lots checked before fills/cashmutation.
-Joined rows cannot hide missing/changed sources, invent vendorflags, or waive delisting dependencies; unknown state fails.
-Nativeerrors/input or outputmutation at setup/case/publication cannot publish annualROIor complete terminal; actualJSONbuffers authenticated.

### Task 1: Lazy known amendment and frozen selection reconstruction

**Files:** Create `src/stock_rsi/operating_amendments.py`, `tests/test_operating_amendments.py`; knownmetadata/payloadJSON.
**Interfaces:** `apply_known_amendments(observation,as_of,metadata,loader,mode)` -> `(observation,receipts)`; `reform_receipts(receipts,metadata,loader,mode)` -> `(targets,receipts)`.
- [ ] Write failing tests: prepublication/currentday15:05/observedmode no monetaryread; visible correctedscore and immutableoriginal; laterFYskip; badsource/proofdigest/componentdelta reject; reconstruction selection mismatch reject.
- [ ] Run `PYTHONPATH=src:. RP -m unittest tests.test_operating_amendments -v`: missingfeatureRED.
- [ ] Implement pure adapter/reform with exactFraction/digest and originalselectionchecks. Run targeted/fullsuiteGREEN, commit.

### Task 2: Market semantics, source-bound runner and actual replay

**Files:** Create `src/stock_rsi/mainboard_daily_proxy.py`, `scripts/replay_low_operating_proxy_targets.py`, `scripts/run_low_operating_proxy_pre2026.py`, `tests/test_low_operating_proxy_account.py`, request/review/results/checks.
**Interfaces:** `execution_rows(day,bars,pending_orders,policy)` -> brokeropenrows; `simulate_low_operating_proxy(...)` existingbudgetedreplay signature pluspolicy; runner `context/authenticate/run` -> frozenconditionalcaseoutputs.
- [ ] Write failing tests: centrounded10%/5%, limitbuys/sellsblocked, permissions/code/date/buycap, suspendednoprices; realbrokerT+1/lots/cash; derivativecash/share/lifecycle/nativefailure; runnerbothcostsbeforeROI/inputmutation/failureterminal.
- [ ] Run targeted missingfeatureRED; implement helper/newderivative/runner; targeted/fullsuiteGREEN, syntheticonly commit.
- [ ] One fresh whole-change reviewer; one testedImportant/Criticalfixpass/fullsuite; record everyruling/cost/deferredminor, no rereview.
- [ ] Freeze fullrequest/currentmethods/spec/plan/review/metadata+payload; push/exactremoteverify; actualrunoncefresh, originaltargetparity andbothcosts beforeROI. Rootrehashfullgraph/captured/publicevidence; reportpassorfailure honestly.
- [ ] Native taskdone/fullsuite; finalpush/exactremote/3CIgreen; archiveonlythisplanworkspace. Fullgoalactive unless allthreeperiodsactuallyverified.

## Self-review

Two independent units share only the amended receipt/target contract. Account cannot proceed until target parity; old source projection supplies components but explicitly no native state assurance. Single final review covers both units and the boundary.
