# Unchanged price-delay strategy: complete registry allocation envelope

The frozen `price_delay_d1` strategy does not meet the interim requirement
2024 > 0, 2025 > 0, 2026 >= 10%. Both 2026 allocation paths are negative under both
frozen extra-cost profiles. This result is a daily engineering diagnostic through
2026-10-20; the full October objective remains unfinished.

| Extra cost, in addition to base fees | 2024 net return | 2025 net return | 2026 through October 20 net return, all paths |
| --- | ---: | ---: | ---: |
| 20bp | +17.507410% | +4.578358% | -0.593779% to -0.587387% |
| 40bp | +15.670055% | +4.107628% | -1.937755% to -1.934805% |

The 2026 denominator is the same continuous account's2025 year-end equity:
CNY 1228873.2000 at 20bp and CNY 1204213.5000 at 40bp. No annual reset, normalized
factor P&L, initial-capital denominator or annualization is used. Each cost has
one root branch point and both complete 361/362-capital-share leaves. Every
leaf has 676 explicit sessions and 34 monthly intentions. Original 95% weights,
integer allocator, orders, source events, costs and unsigned ST capability stay
unchanged. The branch choice never enters an investment snapshot.

## Freeze, completeness and evidence

Implementation/request commit `b5f57800af6031429d67c874c179643795ee43ef` was
pushed before any new complete-tree account or annual result. The request SHA
is `f19acde4f990f44bb7d177c8a43c6a53dd1fbed65495cdd30cd7d8b734ab6d95`.
The request fixes 128 nodes per cost; three were needed for each. No path was
chosen or pruned by performance. All four complete leaves passed the frozen
conservation, source schedule, physical fill-source, original 486/24, 541/27 and
584/30 prefix gates before any annual scorer was called. All 553 bound inputs
passed final authentication. The separate run produced 65 immutable output files.

Code review found and closed four important gaps before freezing: a coherently
omitted candidate branch; unconsumed or delayed corporate flows; an initial
write error bypassing source postchecks; and fills not directly checked against
the original tradable raw open. The 863-test full suite passed locally and in a
clean research environment, with only three optional Qlib skips there. The
freeze's GitHub CI passed all three jobs.

The independent standard-library audit called no production account,
reconciler or scorer. It reconstructed all four physical ledgers and all 34
decision snapshots per leaf; every leaf has 1,375 corporate records. It checked
553 input hashes, 65 new output hashes and 83 prior complete/failed artifacts.
Six semantic negative controls were rejected. The root reran the audit and
obtained the identical report SHA
`3f73ad173a760ba6101bdecf980808b693cc1b2f43e7603b9c06bcfb3a90597b`.
Actual ST orders occurred only in the earlier 5% epoch and were refused for
missing account permission. The July 10% epoch had no actual ST orders; do not
describe it as exercised execution.

Published evidence:

- [Frozen request](../../experiments/qlib/price-delay-registry-envelope-request.json)
- [Final code review](../../experiments/qlib/price-delay-registry-envelope-code-review-final.json)
- [Every leaf and complete return ranges](../../experiments/qlib/price-delay-registry-envelope-results.json)
- [Output hashes and independent run verification](../../experiments/qlib/price-delay-registry-envelope-run-verification.json)
- [Independent ledger and tree audit](../../experiments/qlib/price-delay-registry-envelope-independent-audit.json)
- [Preserved strict registry failure](../../experiments/qlib/price-delay-regime-horizon-results.json)
- [Explicit allocation assumptions](registry-allocation-envelope-design-2026-10-21.md)

## Limits and next research boundary

The 361/362 outcomes are a conservative local engineering envelope under printed
precision assumptions. They are not certified actual CSDC allocations, joint
register states or probabilities. The original strict registry failure remains
unaltered. Actual historical data arrival, full PIT and issuer-state chronology,
queue/impact calibration and true FIFO tax liability remain unverified. The
previously exposed 2026 interval is not a sealed holdout.

Keep this result as a failed interim candidate. Do not inspect its 2026 winning
names, loss periods or events to modify the rule. Any next candidate must have
its economic mechanism, development comparison, parameters, source scope and
selection frozen using pre-2026 evidence before another 2026 account result is
read. The objective remains open.

The separate [development-only evidence inventory](../../experiments/qlib/next-pre2026-candidate-evidence-index.json)
found no credible frozen untested alpha queue. Old source-completion work and
previously evaluated methods must retain their actual stage labels.
