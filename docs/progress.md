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
