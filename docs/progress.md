# Execution ledger — plan: docs/plans/2026-10-11-bootstrap.md

- User authorized new project, plan and direct implementation; first market A-share.
- Isolation: fresh independent repository on codex/bootstrap, staging in /private/tmp.
- Persistent destination: /Users/calm/dev/git_repo/stock-rsi-lab.
- Spec is the authority; v0.1 factor catalogue is a research reference only.
- Pre-flight interfaces: Dataset→Scheduler→Runner; Snapshot→Agent→Decision→Broker;
  runner report→campaign. Stable serialized contracts will be verified per task.
- Baseline: empty new project; no existing production tests. Standard library chosen.

