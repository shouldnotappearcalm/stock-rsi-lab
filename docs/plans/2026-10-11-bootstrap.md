# A股时点回放闭环 Implementation Plan

> For agentic workers: implement task by task with TDD; do not spawn workers
> without the controller's instruction. The user authorized direct execution.

**Goal:** build and run an A-share historical clock/snapshot/wakeup/decision/
account regression loop, then exercise Codex and bounded skill proposals.

**Architecture:** immutable dated inputs feed explicit session scheduling and
point-in-time snapshots. Agents see only serialized snapshots. The evaluator
owns execution, accounts, manifests, and campaign feedback.

**Tech Stack:** Python 3.11+ standard library, unittest, Decimal, zoneinfo, JSON;
Codex CLI is optional and opt-in. No required cloud credentials or pip installs.

**Spec:** `docs/specs/2026-10-11-first-loop.md`.

## Global Constraints

- First market is A-share ordinary mainboard stocks; no live orders.
- Aware timestamps; explicit exchange sessions; event<=public<=available.
- Runtime cannot obtain future rows through snapshots; evidence belongs to the wake.
- Synthetic and real engineering datasets have distinct manifest evidence levels.
- Next-session execution, 100-share buys, T+1 sells, no cash overdraft.
- CLI errors, tool activity, mismatched replay and invalid schema fail closed.
- Existing a-share-skill repository is not modified; publish independent repo.

## Review Focus

- Arrival exactly at cutoff and later revisions must not leak backward.
- Holiday/lunch wakes must not create sessions or impossible fills.
- A failed decision stays in run records, not silently dropped.
- A new skill invalidates recorded responses and sealed-test access remains denied.
- CLI output and subprocess failures must not become valid zero-cost decisions.

## Task 1: Time, calendar and immutable snapshots

Files: `src/stock_rsi/time.py`, `calendar.py`, `data.py`,
`tests/test_time_data.py`, `data/fixtures/synthetic_cn_v1.json`.

Interfaces: `parse_time(str)->datetime`; `TradingCalendar(sessions)` with
`next_open(after)` and `is_trading(at)`; `Dataset.load(path)`;
`Dataset.snapshot(as_of)->Snapshot` with payload and SHA256.

- [x] Write literal cutoff/holiday/lunch/revision/future-perturbation tests.
- [x] Run tests and observe missing implementation failures.
- [x] Implement validation, temporal filtering, revision and immutable snapshots.
- [x] Run all unittest tests, record evidence, commit.

## Task 2: Wake scheduling, decisions and account execution

Files: `scheduler.py`, `models.py`, `broker.py`, `tests/test_schedule_broker.py`.

Interfaces: `schedule(dataset,calendar,start,end,holding)->list[Wake]`;
`Decision.from_dict(payload,snapshot)`; `Broker.submit(decision,at)`;
`Broker.on_open(bar)`; `Broker.snapshot()`.

- [x] Test exact wake timestamps/reasons/dedup, schema and T+1/limit/holiday fills.
- [x] Observe RED; implement minimal rules and explicit errors.
- [x] Verify real ledger results with Decimal and full suite; commit.

## Task 3: Backtest runner, replay, CLI and regression provenance

Files: `runner.py`, `skill.py`, `cli.py`, `__main__.py`,
`tests/test_runner.py`, `skills/trend-pullback/skill.json`, `README.md`.

Interfaces: `run(dataset_path,config,agent,out_dir)->RunReport`;
`replay(run_dir,out_dir)->RunReport`; CLI `run`, `snapshot`, `replay`, `compare`.

- [x] Test hand-derived end-to-end fills, immutable records and request mismatch.
- [x] Observe RED, implement and run the complete fixture backtest/replay.
- [x] Add schema/provenance docs; full tests and commit.

## Task 4: Codex CLI adapter and real-price engineering sample

Files: `agents.py`, `scripts/fetch_real_price_smoke.py`,
`schemas/decision.json`, `tests/test_agents.py`, `docs/data-contract.md`.

Interfaces: `CodexAgent.decide(snapshot,wake,account)->Decision` with timeout,
raw events, tool rejection and schema checks; explicit optional live smoke command.

- [x] Test process/schema/error handling through a local executable fixture.
- [x] Observe RED and implement adapter; preserve bounded stdout/errors.
- [x] Run actual installed Codex CLI on a historical snapshot, record outcome.
- [x] Fetch real-price sample if available, run engineering backtest, label gaps.
- [x] Full tests and commit.

## Task 5: Bounded improvement campaign and independent review

Files: `campaign.py`, `tests/test_campaign.py`,
`docs/experiments/first-hypothesis.md`, `docs/progress.md`.

Interfaces: `run_campaign(dataset,split,arms,budget,out_dir)`; restricted skill
patch validation; complete candidate ledger; sealed data refuses access.

- [x] Test equal candidate counts, invalid patches, shuffled feedback and test denial.
- [x] Observe RED, implement fixed/grid/random/evidence/shuffled controls.
- [x] Run offline regression comparison and one Codex proposal smoke.
- [x] Full suite, independent code review, fix important findings with RED→GREEN.
- [x] Publish repository and final validation/status; no claims of financial efficacy.

