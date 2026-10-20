# Low-beta60 intraday development Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confirm the same low-beta policy under the existing nested physical execution engine on2024/25 before any2026 work.

**Architecture:** A complete-prefix adapter reuses existing TapeBank behavior with one authenticated capture, checking source bytes even on cache hits. A candidate-specific runner binds all prior source/daily-account/audit artifacts, recompiles the same179 events and runs the fixed6 profiles. Independent stdlib ledger audit rederives source events, parent sizing, children, cash and all annual outcomes.

**Tech Stack:** Python3.11/Decimal, existing stock_rsi execution/account modules, no dependencies.

**Spec:** docs/research/low-beta60-intraday-development-plan-2026-10-21.md

## Global Constraints

- Only2023-12-29..2025-12-31;69originalnames,24targets,179events,1332admittedminute pairs.
- Capital1000000CNY;participation_bps[100,500,1000] x extra_cost_bps[20,40];all3extra40 references mustpass bothyears>0 andmeanexposure>=90.
- Existing investment,broker,distribution,tax,calendar,sharedreplay code unchanged;no2026/noorders/nonetwork/nobackground.

## Review Focus

- A cached tape changed on disk must reject;future/missing identities fail before delivering observations.
- Gate must reject a missing/invalid/nonfinite/losing reference and cannot choose the best participation or20bps result.
- Parent quantities are prior-close feedback,not resized using nextdayprices;child buys cannot spend future samewindow sales.
- Partial/failed accounts retain state/artifacts and cannot be silently dropped.
- Completed minute/source evidence is authenticated before any account return is computed.

### Task 1: Source adapter and fixed six-profile replay

**Files:** Create scripts/run_low_beta60_intraday_development.py; tests/test_low_beta60_intraday_development.py; experiments/qlib/low-beta60-intraday-development-plan.json.

**Interfaces:** `CompletePrefixTapeBank(capture:Path,bars:dict,end:str='2025-12-31')` inherits existing TapeBank observation semantics; `__call__(code:str,day:date)->list[dict]` rechecks bytes before any cache return. `confirmation_passes(results:dict)->bool` checks exact6keys andall40bp outcomes. CLI --source-root --plan --expected-plan-sha256 --output-dir emits6profiledirs +summary;accountfactory uses existing IntradayBroker andStockDistributionAccount.

- [ ] Write meaningful adapter/clock/cache mutation and gate all-reference tests, observe RED for missing interface.
- [ ] Implement source authentication and fixed runner;run `PYTHONPATH=src python -m unittest discover -s tests -v`, all pass.
- [ ] Freeze method/source/evidence/entire6profile protocol SHA,commit+push before actual account;run once foreground, preserve all failures.

### Task 2: Independent account validation and publication

**Files:** Create experiments/qlib/audit_sources/2026-10-21-low-beta60-intraday-development-audit.py; actual results/audit/verification JSON; result doc;update objective.

**Interfaces:** stdlib auditor consumes B/low-beta60-intraday-development-20261021 plus all original sources and plan;CLI --source-root --run-dir --output produces independent report;does not import production modules/runstrategy.

- [ ] Reconstruct each full account fromraw source,events and sampled windows;authenticate all snapshot,parent/child/fee/quantity/cash/residual/time records;meaningful no-hash semantic tamper controls.
- [ ] One fresh final reviewer covers whole code/runs/audits;fixCritical/Important withRED->GREEN andfull suite, record scope limits.
- [ ] Publish all6outcomes including failures;keep objective active unless all three full requested periods actually verified;push.
