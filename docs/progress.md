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

- 2026-10-14 data search: cloned and inspected BaoStock downloader, Tushare SDK,
  AKShare, Qlib and `chenditc/investment_data`; downloaded the 2026-10-13
  `qlib_bin.tar.gz` release (567,791,316 bytes) and its manifest.
- Archive validator and SHA-256 passed. Extracted calendar/instruments plus three symbol
  samples; 6,166 observed intervals, 5,560 filtered A-share equities on 2026-10-13.
- Added dependency-free Qlib audit reader. It reconstructs raw OHLCV, excludes known
  indices/B shares and refuses to infer tradability from missing bars.
- Data ruling: frozen price layer is usable for engineering replay. Security master,
  suspension, legal limits, corporate-action ledger and PIT financial revisions still
  block research promotion; third-party data is not committed to the public repository.
- Cloned CNEquity at `c118038e` and SimTradeData at `b925da2f`. CNEquity's real
  TDX demo wrote 150 bars and exactly matched Qlib for 600519 on 2026-10-13.
- CNEquity/BaoStock historical status probes wrote 2,140 rows for five normal names and
  1,284 rows for three edge names across 428 sessions. Coverage receipts were complete;
  observed both ST+suspension and a later ST transition.
- Ruling: first research universe is SH/SZ mainboard. Qlib/Dolt's limit table stops in
  2023, so 2025–2026 exact daily price limits remain the immediate data blocker.
- 2026-10-14 methodology correction: 2026 test facts were used to suggest later
  high-exposure methods. Those methods/results were removed before commit and push.
  The 2026-01-05—2026-10-13 window is permanently marked contaminated and cannot
  validate future versions. Registered the 20% net-return / 90% exposure target for a
  new prospective sealed window that starts only after complete method freeze.
- 2026-10-15 external-method search: reviewed Qlib Alpha158/DoubleEnsemble and listwise
  ranking evidence, then ran Qlib strictly through 2025-12-30. The retained development
  portfolio is DoubleEnsemble CSI500 Top-100/Drop-2: 27.13% net compound annualized,
  99.58% average exposure, -20.12% drawdown, 2.23% initial-capital cost. It passes the
  two-year development target but not the 20%-per-calendar-year robustness target.
- User-directed frozen replay: loaded the unchanged pre-2026 DoubleEnsemble model and retained
  Top-100/Drop-2 portfolio, then ran 2026-01-05—2026-10-13 once without retraining. Net return
  was -2.00%, CSI500 -5.10%, excess +3.10%, exposure 99.42%, drawdown -16.30%. The +20%
  absolute target failed. The consumed interval remains diagnostic-only and cannot select a
  revised method.
- Continued evolution without reading or rerunning 2026: froze the DoubleEnsemble predictions and
  mutated only portfolio construction to weekly CSI500 enhanced indexing. Built 727 capped index-
  weight sessions and 484 trailing risk snapshots, then exhausted a fixed six-candidate budget.
  The retained development candidate returned 21.43% in 2024 and 49.17% in 2025 (34.67% net
  annualized), with 97.74% average exposure and -18.88% drawdown. A clean process reproduced the
  metrics within 1e-12. The audited CLARABEL path never relaxed constraints; one infeasible
  candidate consumed its slot. The result remains development-only and the next valid outcome
  test must use a newly registered future interval.
