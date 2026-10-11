# stock-rsi-lab

Build an A-share research harness with explicit simulated time. Read
`docs/specs/2026-10-11-first-loop.md` and the current implementation plan.

- Never read future records through a decision-facing API. Both publication
  and observed arrival time govern visibility; report period is not visibility.
- The dataset, account, clock and evaluator are outside the editable skill.
- Use timezone-aware timestamps and an explicit exchange session table. Do not
  invent sessions from weekdays or treat lunch as continuous trading.
- Distinguish synthetic regression fixtures, real-price engineering samples
  and verified point-in-time research datasets in every run manifest.
- Do not expose credentials, submit broker orders or launch background jobs.
- Changes need behavior tests. Run `PYTHONPATH=src python -m unittest discover
  -s tests -v`. Keep fixtures and their provenance versioned.
- Runtime adapter errors and invalid decisions fail closed; no free-text orders.
- An external CLI's read-only sandbox is not an OS-level future-data boundary.
  CLI runs remain engineering-only until a stronger boundary is demonstrated.

