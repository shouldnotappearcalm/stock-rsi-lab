# Portfolio Proposal Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the typed factor, policy-bundle and whole-portfolio proposal foundation needed for v0.2, including deterministic target-to-order execution and replay, without replacing the existing single-decision path.

**Architecture:** New focused modules sit beside the legacy runner. Factor evidence is bound to one snapshot; policy bundles are content-addressed declarative artifacts; policies emit multiple complete portfolio proposals including `keep-current`; a selector chooses one proposal; and a target planner produces a batch of sell-first/buy-second orders for the existing broker. A new portfolio runner records candidates, selection and orders while the legacy CLI and replay remain regression-compatible.

**Tech Stack:** Python 3.11+ standard library, `dataclasses`, `Decimal`, `typing.Protocol`, JSON, SHA-256, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-14-policy-outcome-rsi-design.md`

## Global Constraints

- Daily-frequency A-share research only; no live orders, credentials or broker connectivity.
- All decision inputs come from one point-in-time `Snapshot`; evidence IDs must be visible in it.
- The evaluator, account, broker, clock and data ledger remain outside evolvable policy bundles.
- Project-owned code is Apache-2.0; raw/vendor data, local caches and large run artifacts remain ignored.
- New serialized objects use canonical JSON, finite values, explicit versions and SHA-256 identities.
- Weights are long-only `Decimal` strings quantized to six decimal places and total exactly `1.000000`, including exactly one `CASH` target.
- The foundation does not implement a claimed investment strategy or Outcome Model; tests use literal policies and selectors.
- Existing `run`, `replay`, `snapshot`, `compare` and `priority` behavior must remain unchanged.
- Run verification: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest discover -s tests -v`.

## Review Focus

- Reject bool/NaN/infinity, duplicate factor keys, contradictory value/missing states and evidence absent from the snapshot; Task 1 tests all five cases.
- Reject portfolio targets with duplicate securities, absent or duplicate `CASH`, ineligible securities, negative weights or totals other than exactly `1.000000`; Task 2 tests each condition.
- Reject proposal reuse against another snapshot, account or policy bundle; Task 2 checks all three hashes before any selection or order planning.
- Execute a same-open rebalance with eligible sells before buys, while preserving T+1, price-limit and cash invariants; Task 4 uses a hand-calculated mixed rebalance.
- Refuse replay if candidates, selector result, bundle content or batch-order sequence changes, while preserving all legacy replay tests; Task 5 covers each identity and runs the complete suite.

---

## File map

| File | Responsibility |
| --- | --- |
| `src/stock_rsi/factors.py` | Typed factor evidence and snapshot-bound factor frames |
| `src/stock_rsi/portfolio.py` | Target weights, portfolio proposals, account identity and keep-current proposal |
| `src/stock_rsi/policy.py` | Policy bundle loading/identity plus policy and selector protocols |
| `src/stock_rsi/targeting.py` | Convert one selected target portfolio into deterministic trade decisions |
| `src/stock_rsi/portfolio_runner.py` | Candidate/selection/batch-execution event loop and replay |
| `src/stock_rsi/broker.py` | Same-open batch execution with sells before buys; existing `on_open` compatibility |
| `schemas/factor-evidence.json` | Public factor-evidence contract |
| `schemas/portfolio-proposal.json` | Public proposal contract |
| `policies/v0.2-contract-fixture/` | Non-investment fixture bundle proving content identity and module boundaries |
| `tests/test_factors.py` | Factor contract tests |
| `tests/test_portfolio.py` | Proposal and account-binding tests |
| `tests/test_policy_bundle.py` | Bundle identity and protocol tests |
| `tests/test_targeting.py` | Target planning and batch broker tests |
| `tests/test_portfolio_runner.py` | End-to-end candidate recording and replay tests |
| `LICENSE` | Apache-2.0 text for project-owned code |
| `.github/workflows/tests.yml` | Public standard-library test workflow |

### Task 1: Snapshot-bound factor evidence

**Files:**
- Create: `src/stock_rsi/factors.py`
- Create: `schemas/factor-evidence.json`
- Create: `tests/test_factors.py`

**Interfaces:**
- Consumes: `stock_rsi.data.Snapshot`, `stock_rsi.data.canonical`, `stock_rsi.data.digest`, `stock_rsi.time.parse_time`.
- Produces: `FactorEvidence.from_dict(data: dict, snapshot: Snapshot) -> FactorEvidence`; `FactorFrame.from_evidence(snapshot: Snapshot, evidence: list[FactorEvidence]) -> FactorFrame`; `FactorFrame.get(factor_id: str, security_id: str) -> FactorEvidence`; immutable `to_dict()` and `sha256` properties.

- [ ] **Step 1: Write failing validation tests in `tests/test_factors.py`**

  Add `test_factor_evidence_is_snapshot_bound_and_round_trips`, asserting one visible price factor preserves `factor_id`, `security_id`, decimal value, unit, `as_of`, lookback, evidence IDs and snapshot hash through `to_dict()`. Add table-driven invalid cases for bool/NaN/infinity, invisible evidence, mismatched `as_of`, empty units, value plus `missing_reason`, and neither value nor `missing_reason`.

- [ ] **Step 2: Run Task 1 tests and observe RED**

  Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest tests.test_factors -v`

  Expected: import failure for `stock_rsi.factors`.

- [ ] **Step 3: Implement `FactorEvidence`**

  In `src/stock_rsi/factors.py`, define a frozen dataclass with exact fields `factor_id`, `security_id`, `value`, `unit`, `as_of`, `lookback_sessions`, `evidence_ids`, `quality_flags`, `missing_reason`, `snapshot_hash`. Store present numeric values as canonical finite decimal strings; missing values use `None` plus a nonempty reason. Require `as_of` to equal the snapshot `as_of`, positive integer lookback or zero for timeless identity/status evidence, and all evidence IDs to exist in the snapshot.

- [ ] **Step 4: Write failing frame tests**

  Add `test_factor_frame_rejects_duplicates_and_cross_snapshot_evidence`, asserting duplicate `(factor_id, security_id)` keys fail, factor evidence from another snapshot fails, ordering does not change `sha256`, and `get()` raises `KeyError` for absent factors.

- [ ] **Step 5: Implement `FactorFrame` and public schema**

  `FactorFrame.from_evidence` sorts by `(factor_id, security_id)`, binds the frame to `snapshot.sha256`, serializes only canonical values and rejects duplicate keys. Write `schemas/factor-evidence.json` with `additionalProperties: false` and the same field names/types.

- [ ] **Step 6: Verify Task 1 and the complete suite**

  Run the Task 1 command, then the global test command. Expected: Task 1 and all existing tests pass.

- [ ] **Step 7: Commit Task 1**

  ```bash
  git add src/stock_rsi/factors.py schemas/factor-evidence.json tests/test_factors.py
  git commit -m "feat: add snapshot-bound factor evidence"
  ```

### Task 2: Whole-portfolio proposal contract

**Files:**
- Create: `src/stock_rsi/portfolio.py`
- Create: `schemas/portfolio-proposal.json`
- Create: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `Snapshot`, account dictionaries returned by `runner.account_view`, eligible security IDs and a caller-supplied `policy_bundle_id`.
- Produces: `account_hash(account: dict) -> str`; `TargetWeight.from_dict(data: dict) -> TargetWeight`; `PortfolioProposal.from_dict(data: dict, snapshot: Snapshot, account: dict, eligible: set[str], policy_bundle_id: str) -> PortfolioProposal`; `keep_current_proposal(snapshot: Snapshot, account: dict, policy_bundle_id: str, evidence_ids: list[str], expires_at: datetime) -> PortfolioProposal`.

- [ ] **Step 1: Write failing valid-proposal tests**

  Add `test_proposal_is_bound_to_snapshot_account_policy_and_complete_weights`. Use targets `CASH=0.400000`, `SYN_A=0.600000`; assert exact canonical round trip, six-decimal strings, target ordering independent identity, evidence visibility, and distinct proposal/account hashes.

- [ ] **Step 2: Run Task 2 tests and observe RED**

  Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest tests.test_portfolio -v`

  Expected: import failure for `stock_rsi.portfolio`.

- [ ] **Step 3: Implement target/account identities and proposal validation**

  `TargetWeight` accepts only exact fields `security_id` and `weight`; rejects bool, exponent strings, more than six decimal places, negative values and values above one. `PortfolioProposal` requires exact fields `schema_version`, `proposal_id`, `policy_bundle_id`, `snapshot_hash`, `account_hash`, `targets`, `horizon_sessions`, `expires_at`, `evidence_ids`, `rationale`, `constraints`, `construction`; use schema version `portfolio-proposal-v1`, positive horizon, aware expiry after snapshot time and canonical JSON objects for constraints/construction.

- [ ] **Step 4: Write failing adversarial target tests**

  Add `test_proposal_rejects_invalid_targets_and_identity_reuse`. Exercise duplicate security, missing/duplicate `CASH`, unknown security, negative or over-one weight, total `0.999999`, invisible evidence, wrong snapshot hash, wrong account hash and wrong policy ID.

- [ ] **Step 5: Implement `keep_current_proposal` and schema**

  Compute current weights from `cash`, each position's `quantity * mark_price`, and `equity`; reject unmarked or nonconserving accounts. Quantize to six places using largest-remainder allocation so targets total exactly one and use deterministic security-ID tie breaks. Publish the equivalent JSON Schema.

- [ ] **Step 6: Verify Task 2 and the complete suite**

  Run Task 2 tests, then the global test command. Expected: all pass.

- [ ] **Step 7: Commit Task 2**

  ```bash
  git add src/stock_rsi/portfolio.py schemas/portfolio-proposal.json tests/test_portfolio.py
  git commit -m "feat: define whole-portfolio proposal contract"
  ```

### Task 3: Content-addressed policy bundles and protocols

**Files:**
- Create: `src/stock_rsi/policy.py`
- Create: `policies/v0.2-contract-fixture/manifest.json`
- Create: `policies/v0.2-contract-fixture/universe_filter.json`
- Create: `policies/v0.2-contract-fixture/regime_policy.json`
- Create: `policies/v0.2-contract-fixture/candidate_ranker.json`
- Create: `policies/v0.2-contract-fixture/entry_policy.json`
- Create: `policies/v0.2-contract-fixture/exit_policy.json`
- Create: `policies/v0.2-contract-fixture/portfolio_constructor.json`
- Create: `policies/v0.2-contract-fixture/execution_policy.json`
- Create: `tests/test_policy_bundle.py`

**Interfaces:**
- Consumes: factor schema IDs, canonical JSON module files and parent bundle ID.
- Produces: `PolicyBundle.load(path: str | Path) -> PolicyBundle`; `PolicyBundle.bundle_id`; `PolicyBundle.module(name: str) -> dict`; runtime-checkable `FactorProvider` protocol with `version` and `build(snapshot, wake, account) -> FactorFrame`; runtime-checkable `PortfolioPolicy` protocol with `bundle_id` and `propose(snapshot, wake, account, factors) -> tuple[PortfolioProposal, ...]`; runtime-checkable `ProposalSelector` protocol with `version` and `select(snapshot, account, proposals) -> str`.

- [ ] **Step 1: Write failing bundle identity tests**

  Add `test_policy_bundle_requires_exact_modules_and_hashes_content`. Assert the fixture contains exactly the seven spec module names, module content is immutable to callers, changing any byte changes `bundle_id`, unknown/missing modules fail, and a declared non-null parent must be a 64-character lowercase SHA-256.

- [ ] **Step 2: Run Task 3 tests and observe RED**

  Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest tests.test_policy_bundle -v`

  Expected: import failure for `stock_rsi.policy`.

- [ ] **Step 3: Implement `PolicyBundle` and fixture bundle**

  The manifest exact fields are `schema_version`, `name`, `parent_bundle_id`, `factor_schema_ids`, `modules`, `description`. Use schema `policy-bundle-v1`; module paths must be simple basenames under the bundle directory, symlinks and traversal are rejected, JSON must be an object, and `bundle_id` hashes the manifest plus canonical module contents. Each fixture module has exact fields `schema_version`, `module`, `mode`, `parameters`, with values `policy-module-v1`, its manifest key, `CONTRACT_ONLY` and `{}`. The fixture description must state `CONTRACT_ONLY_NOT_AN_INVESTMENT_STRATEGY`.

- [ ] **Step 4: Write protocol/candidate-set tests**

  Add `test_policy_and_selector_protocols_require_multiple_valid_candidates`. A literal test policy returns `keep-current` and one alternative; validate unique IDs, at least two proposals, one exact `keep-current`, common snapshot/account/policy identities and selector output belonging to the candidate set. Include invalid duplicate, one-candidate and unknown-selection cases.

- [ ] **Step 5: Implement protocol helpers**

  Add `validate_candidate_set(policy: PortfolioPolicy, snapshot, account, proposals) -> tuple[PortfolioProposal, ...]` and `select_proposal(selector: ProposalSelector, snapshot, account, proposals) -> PortfolioProposal`. These helpers perform cross-candidate checks and never infer a fallback if the selector returns an unknown ID.

- [ ] **Step 6: Verify Task 3 and the complete suite**

  Run Task 3 tests, then the global test command. Expected: all pass.

- [ ] **Step 7: Commit Task 3**

  ```bash
  git add src/stock_rsi/policy.py policies/v0.2-contract-fixture tests/test_policy_bundle.py
  git commit -m "feat: add content-addressed policy bundles"
  ```

### Task 4: Deterministic target orders and same-open batches

**Files:**
- Create: `src/stock_rsi/targeting.py`
- Modify: `src/stock_rsi/broker.py`
- Create: `tests/test_targeting.py`
- Modify: `tests/test_schedule_broker.py`

**Interfaces:**
- Consumes: a validated selected `PortfolioProposal`, decision snapshot, current account view and all security bars for one open.
- Produces: `plan_target_orders(proposal: PortfolioProposal, snapshot: Snapshot, account: dict) -> tuple[Decision, ...]`; `Broker.on_market_open(bars: list[dict]) -> list[dict]`; backward-compatible `Broker.on_open(bar: dict) -> list[dict]`.

- [ ] **Step 1: Write failing target-planning tests**

  Add `test_target_planner_emits_exits_before_entries_with_stable_rounding`. Starting with 200 shares of `SYN_A`, cash and visible closes for `SYN_A`/`SYN_B`, target `SYN_A=0`, `SYN_B=0.600000`, `CASH=0.400000`; assert one full sell followed by a 100-share-lot buy, evidence copied from the proposal, security-ID-stable ordering within action, and no zero-quantity decision.

- [ ] **Step 2: Run Task 4 tests and observe RED**

  Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest tests.test_targeting -v`

  Expected: import failure for `stock_rsi.targeting` or missing `Broker.on_market_open`.

- [ ] **Step 3: Implement target-to-decision planning**

  Translate target value at visible close into desired shares. Buys round down to 100-share lots; sells may liquidate an existing odd lot. Require current visible close for every nonzero target and every held security being reduced. Output all `SELL` decisions sorted by security, then all `BUY` decisions sorted by security. The plan is an intent; final affordability remains the broker's responsibility at next open.

- [ ] **Step 4: Write failing same-open broker tests**

  Add `test_market_open_sells_before_buys_and_preserves_t1_limits_and_cash`. Hand-calculate a rebalance where the buy is affordable only after an eligible sell. Assert sell then buy fills, exact fees/cash, no overdraft, T+1 blocks same-day acquired lots, missing bar leaves the affected order explicitly invalid, and limit/suspension behavior matches existing `on_open` semantics.

- [ ] **Step 5: Implement `Broker.on_market_open`**

  Validate unique securities and one shared explicit session date for the bar batch before mutation. Process pending eligible sells against their bars, then buys, each with the current `on_open` constraints. Refactor the single-security logic into private helpers; retain `on_open(bar)` behavior and all existing serialized statuses.

- [ ] **Step 6: Verify Task 4 and the complete suite**

  Run Task 4 tests, `tests.test_schedule_broker`, then the global test command. Expected: all pass and existing hand-calculated cash remains unchanged.

- [ ] **Step 7: Commit Task 4**

  ```bash
  git add src/stock_rsi/targeting.py src/stock_rsi/broker.py tests/test_targeting.py tests/test_schedule_broker.py
  git commit -m "feat: execute deterministic portfolio target batches"
  ```

### Task 5: Candidate-recording portfolio runner and replay

**Files:**
- Create: `src/stock_rsi/portfolio_runner.py`
- Create: `tests/test_portfolio_runner.py`
- Modify: `src/stock_rsi/verification.py`
- Modify: `docs/data-contract.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `Dataset`, run configuration, `PortfolioPolicy`, `ProposalSelector`, `FactorFrame` provider and output directory.
- Produces: `run_portfolio(dataset_path, config, policy, selector, factor_provider, out_dir) -> dict`; `replay_portfolio(run_dir, out_dir) -> dict`; report fields `candidate_sets`, `selections`, `orders`, `fills`, `account`, `verify_gate`, and version/hash manifests.

- [ ] **Step 1: Write failing end-to-end candidate recording test**

  Add `test_portfolio_run_records_all_candidates_before_selection_and_rebalances`. Use the synthetic dataset, literal factor provider, literal two-candidate policy and explicit selector. Assert every selection references a previously serialized candidate-set hash; selected targets generate the expected order batch/fills/account; unselected candidate outcomes are not labeled observed; output directories are exclusive.

- [ ] **Step 2: Run Task 5 tests and observe RED**

  Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest tests.test_portfolio_runner -v`

  Expected: import failure for `stock_rsi.portfolio_runner`.

- [ ] **Step 3: Implement `run_portfolio`**

  Reuse existing scheduling, snapshot/account helpers and execution bars without modifying `runner.run`. At each wake: build factors, call policy, validate and write all candidates, call selector, bind the selected proposal hash, plan target orders and submit them. At each open, pass the day's complete bar batch to `Broker.on_market_open`. Manifest identity includes policy bundle, selector version, factor-provider version, candidate-set hashes, source hash and config.

- [ ] **Step 4: Write failing replay/tamper tests**

  Add `test_portfolio_replay_rejects_candidate_selector_bundle_and_order_tampering`. Independently alter an unselected candidate, selection ID, policy bundle file and order sequence; each must fail replay before a success result is returned. Add a future-perturbation test proving later bar changes do not alter an earlier candidate set.

- [ ] **Step 5: Implement `replay_portfolio` and VerifyGate fields**

  Replay uses recorded literal factor frames, candidate sets and selected IDs to recompute target decisions and account execution without calling policy or selector. It validates their request/response hashes and compares candidates, selections, orders, fills, account, errors and VerifyGate. Add hard checks for common proposal identities and selection membership; data-quality warnings remain nonblocking.

- [ ] **Step 6: Document the foundation boundary**

  Update `docs/data-contract.md` and `README.md`: the new runner is an internal/programmatic foundation until an actual investment policy and Outcome Model exist; the `v0.2-contract-fixture` is not a strategy; the legacy CLI remains the runnable public demonstration.

- [ ] **Step 7: Verify Task 5 and the complete suite**

  Run Task 5 tests and the global test command. Expected: all pass, including legacy run/replay/campaign/priority tests.

- [ ] **Step 8: Commit Task 5**

  ```bash
  git add src/stock_rsi/portfolio_runner.py src/stock_rsi/verification.py tests/test_portfolio_runner.py docs/data-contract.md README.md
  git commit -m "feat: add replayable portfolio proposal runner"
  ```

### Task 6: Public license and continuous verification

**Files:**
- Create: `LICENSE`
- Create: `.github/workflows/tests.yml`
- Modify: `pyproject.toml`
- Modify: `README.md`

**Interfaces:**
- Consumes: public repository source and synthetic fixtures only.
- Produces: explicit Apache-2.0 licensing metadata and a GitHub Actions test run on Python 3.11 and 3.12.

- [ ] **Step 1: Add a failing packaging/license assertion**

  Extend `tests/test_cli.py` with `test_public_package_declares_license_and_private_inputs_stay_ignored`: assert `LICENSE` contains the Apache License 2.0 heading, `pyproject.toml` declares the license file, and `.gitignore` still covers `data/local/`, `artifacts/` and `.env`.

- [ ] **Step 2: Run the assertion and observe RED**

  Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest tests.test_cli.CLITests.test_public_package_declares_license_and_private_inputs_stay_ignored -v`

  Expected: FAIL because `LICENSE` is absent.

- [ ] **Step 3: Add Apache-2.0 and package metadata**

  Add the unmodified Apache License 2.0 text; update `pyproject.toml` to `license = {file = "LICENSE"}` and include license files in setuptools metadata. Add `Copyright 2026 stock-rsi-lab contributors` and a short licensing section to the README, distinguishing project code from external data/model terms.

- [ ] **Step 4: Add GitHub Actions**

  Create `.github/workflows/tests.yml` for pushes and pull requests. Use `actions/checkout`, `actions/setup-python` with 3.11/3.12, then run the global standard-library unittest command. Do not fetch private data or invoke Codex/network smokes.

- [ ] **Step 5: Run final verification**

  Run the global test command, `git diff --check`, a tracked-history credential scan, and `git status --short`. Expected: all tests pass, no whitespace errors, no credential findings and no unexpected files.

- [ ] **Step 6: Request independent review**

  Give a fresh reviewer the spec, this plan and `git diff` from `4b30334`; require review of temporal binding, Decimal target conservation, sell-first batch mutation, replay integrity and legacy compatibility. Fix important findings with a failing regression before implementation changes.

- [ ] **Step 7: Commit Task 6**

  ```bash
  git add LICENSE .github/workflows/tests.yml pyproject.toml README.md tests/test_cli.py
  git commit -m "chore: license and continuously test the public project"
  ```

## Deferred follow-on plans

This foundation intentionally leaves these approved-spec slices for separate implementation plans:

1. Deterministic price/risk/liquidity factor runtime and real investment policy skills.
2. Prediction–observation ledger, 5/20/60-session outcome maturity and forecast baselines.
3. Crossed policy/model retention evaluator and recursive lineage.
4. ACP proposal adapters plus equal-budget and shuffled-feedback controls.
5. Historical universe, corporate-action, status and PIT-fundamental data capabilities.
6. Registered walk-forward and prospective experiments.

The foundation must land and stabilize before these plans bind to its serialized contracts.
