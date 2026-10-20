# Low-beta60 minute source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture and admit the complete frozen pre2026 prefix without changing investment rules or querying2026.

**Architecture:** Reuse QueryJournal, prefix_minute_requirements, query_minute_packet and source validation unchanged. New candidate-specific wrapper authenticates existing evidence; a bounded capture function preserves source bytes and cross-restart budget. A separate admission command does not run an account.

**Tech Stack:** Python3.11 stdlib; existing eltdx3.2.3 and stock_rsi helpers.

**Spec:** docs/research/low-beta60-minute-source-plan-2026-10-21.md

## Global Constraints

- Frozen universe69/targets24, required1332, cached839, fresh493; dates2024-01-02..2025-12-31 only.
- Existing QueryJournal max_queries493,max_attempts1; stop3consecutive failures; original request/response/packet bytes immutable.
- Installed eltdx3.2.3; host116.205.183.150:7709; timeout3; delay0.05; single connection,no host probing/heartbeat.
- No2026ROI, account replay, dependencies, broker orders or background processes.

## Review Focus

- Corrupted reused packet must fail before fresh calls.
- Existing successful or failed response must not be refetched after restart.
- Reserved-but-unanswered request must remain consumed and fail closed.
- Restart must not bypass three consecutive failures.
- Future/duplicate requests or caller budget changes must be rejected before source fetch.

### Task 1: Authenticated bounded capture

**Files:** Create scripts/capture_low_beta60_minutes_pre2026.py; tests/test_low_beta60_minute_capture.py; experiments/qlib/low-beta60-minute-capture-plan.json.

**Interfaces:** Consumes existing gap identities, raw/calendar/targets hashes and all reusable manifest SHA. Produces `capture_prefix(base,out,reused,fresh,plan,fetch)` manifest and immutable sessions/queries; CLI flags --source-root --request --plan --expected-plan-sha256 --output-dir. `fetch(code,day)` returns decoded source response; production callback owns one bounded client.

- [ ] Write tests for unchanged reused bytes, one fresh call per identity, restart success/failure reuse, reserved interrupted attempt, stop3 across restart, future/duplicate/overlap rejection and corrupted reuse prefetch rejection.
- [ ] Run `PYTHONPATH=src python -m unittest discover -s tests -p test_low_beta60_minute_capture.py -v`; observe missing interface failure.
- [ ] Implement bounded capture and CLI evidence authentication with existing helpers; preserve partial manifest on abnormal exit.
- [ ] Run full `PYTHONPATH=src python -m unittest discover -s tests -v`; all pass.
- [ ] Freeze code/request/spec/SDK/budget hashes, commit+push before first live source call, then execute foreground with logs; retain all failures.

### Task 2: Complete source admission and publication

**Files:** Create scripts/admit_low_beta60_minutes_pre2026.py; tests/test_low_beta60_minute_admission.py; experiments/qlib/low-beta60-minute-source-results.json and independent audit artifact; update objective JSON.

**Interfaces:** Consumes Task1 manifest/sessions, original raw/calendar/targets, request/plan. `inspect_packet(code,day,packet,daily)` returns existing diagnostic facts plus status or rejects; main emits details and summary independently of account code. CLI flags --source-root --capture-dir --plan --expected-plan-sha256 --output-dir.

- [ ] Write behavior cases for valid source, wrong minute price signature/oversized lower volume, failed/partial/future packet and wrong source identity, using existing complete minute synthetic fixtures.
- [ ] Observe failing test, implement admission using inspect_minutes+aggregate_minutes unchanged, run full suite.
- [ ] Run actual local-only admission, preserving each failure; independent audit exact1332source/request/response identities and economics-free statuses.
- [ ] One fresh final reviewer examines the whole change and actual source evidence. Fix Critical/Important, report remaining bounds, push results and update still-active objective.
