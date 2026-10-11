# Execution ledger — plan: docs/plans/2026-10-11-bootstrap.md

- User authorized new project, plan and direct implementation; first market A-share.
- Isolation: fresh independent repository on codex/bootstrap, staging in /private/tmp.
- Persistent destination: /Users/calm/dev/git_repo/stock-rsi-lab.
- Spec is the authority; v0.1 factor catalogue is a research reference only.
- Pre-flight interfaces: Dataset→Scheduler→Runner; Snapshot→Agent→Decision→Broker;
  runner report→campaign. Stable serialized contracts will be verified per task.
- Baseline: empty new project; no existing production tests. Standard library chosen.

- Task 1 complete: six time/data behaviors observed RED then GREEN; commit be8d53d.
- Task 2 complete: six scheduler/decision/account behaviors observed RED then GREEN;
  full suite 12/12. Execution is next-day morning open, separate from lunch wake.
- Task 3 Ruling: trend is endpoint return over the visible trend window,
  not current/MA; the hand fixture is rising over the window while pulling back.
  Cost if wrong: seed investment style changes; it is an unvalidated baseline.
- Task 3 complete: 9 runner/CLI behaviors RED→GREEN; full suite 21/21.
- Real source probe: Tencent raw day returned 58 rows for 600519 2024Q1;
  volume unit and PIT/corporate actions remain unverified, engineering-only.
- Task 4 runtime finding: CLI 0.139 ignores user config then falls back to unsupported
  gpt-5.4 under ChatGPT auth. Local config/model cache and official docs identify
  gpt-6.1-sol; adapter now passes model explicitly and includes it in run identity.
- Task 4 tests: subprocess schema, tool rejection, errors, timeout, call budget,
  explicit model, raw-only import all RED→GREEN; full suite 28/28.
- Task 4 additional regression: repeated holiday wakes supersede unfilled same-symbol
  intents; previously they accumulated two fills. Reproduced then fixed.

- Task 4 actual success: bundled CLI 0.159.0-alpha.12.1 supports this account/model;
  snapshot decision and bounded skill proposal each completed, with usage and raw events.
- Task 5 complete: fixed/grid/random/evidence/shuffled equal attempts; optional Codex;
  invalid proposals consume slots; development export/registry guards; 43/43 tests.
- Independent review: all material temporal, missingness, replay, subprocess and feedback
  findings reproduced or checked, fixed and re-reviewed; no outstanding important findings.
- Ruling: seed-relative four-patch catalog is a first engineering search, not recursive RSI.
  Cost if mistaken for efficacy: tiny synthetic windows can encourage false investment claims.
- Final runs and review evidence: docs/validation.md. Publish as independent local Git repo;
  retain data/local and artifacts locally, no remote push or broker connection.

- User priority update: run exploratory 2025—2026.10 and 2026 independently first.
- Two-level gate implemented: correctness errors fail; research data assumptions annotate
  exploratory results and cannot establish efficacy. Negative return alone is not failure.
- Added causality-preserving compact snapshots; recent active bars retained per security.
- 50 regressions pass; independent review accounting-conservation finding fixed/rechecked.
- Actual frozen-seed runs: 426/183 sessions, 68/28 fills, final equities 100285.47/100186.26.
- 621/263 wake snapshots; both fixed-response replays completed with matching ledgers.
- No holding/fill exposure at known BYD raw discontinuity; other actions remain unmodeled.
