# Exact float32 source hypothesis: failed full control gate

The frozen local reconstruction did **not** pass. All42 original issuers and
20,089 raw rows were counted.20,031 explicitly trading rows contributed80,124
OHLC cells, including ST rows;58 nontrading rows were explicitly excluded.
80,117 cells had exactly one legal cent tick matching the independent raw
price. Seven cells had no cent tick in the prescribed interval:

| Issuer | Date | Fields | Original raw value |
|---|---|---|---|
| SH600118 | 2024-09-26 | high, close | 22.2900 |
| SH601158 | 2024-09-26 | high, close | 4.5700 |
| SZ002153 | 2024-09-26 | high, close | 6.2600 |
| SZ002195 | 2024-09-26 | open | 2.3800 |

This rejects the precise frozen reconstruction hypothesis. It does not identify
whether upstream normalization, source vintage or another transform explains
the discrepancy, nor establish which provider is correct. No guard was widened,
no failed row/issuer was removed and no price was rounded to force acceptance.

Volume also failed its independent unit check: scale1 mismatched all20,031
trading rows; scale100 mismatched38. Neither prescribed scale passed every row,
so no volume unit was admitted. The38 failures were not treated as tolerance.

The failed price gate prevented **all SZ002326 quote-value decoding**. There is
no target-start marker, projected row or projection file. No account, return,
tax selection or new2026accepted data was produced. The objective remains
2024>0,2025>0,2026Jan–Oct>=10%, and remains unachieved. Historical normalized
development results are not promoted to physical replay acceptance.

## Frozen lineage and verification

Request `experiments/qlib/low-operating-f32-source-request.json`, SHA256
`7efcb46023a967b06918913209ab8c84ccbfb6c5919559d74944c86aec0f804a`, binds551
inputs: the complete preceding source context, original operating request,
physically capped provider fields, methods, spec, plan and review. Freeze commit
`a446475f207029d856d6ab5127870ca8f2deda12` was pushed and independently matched
with `git ls-remote` before the first real control comparison. The runner exited2
with `F32_SOURCE_HYPOTHESIS_NOT_FULLY_VERIFIED`; no retry or alternate rule.

The separate checker derived binary fractions from integer bits without
importing the new producer or bounds module. It independently reconstructed all
controls, exact counters and failed unit hypotheses and returned
`PASS_INDEPENDENT_BIT_SOURCE_RECONSTRUCTION_NOT_ACCOUNT_ADMISSION`, with source
completionfalse. This PASS authenticates the failed experiment, not the source
hypothesis or investment goal.

Root additionally rehashed all552 inputs including the request, all44 captured
files and byte-identical public copies. Inputs and outputs remained unchanged.
The public44-file source tree is `experiments/qlib/low-operating-f32-source-recovery/`.

- Control summary SHA256: `4234b6d3dd60274f7e1ac3a024303fdfcfa6e17c756262d0872b811afc6adb0a`.
- Terminal SHA256: `9e6c05a4b403ba2dcb6e409f2c68d7b6a36a04932b57ad1a3367d44a1dea07e7`.
- Separate check SHA256: `416a2f11372f6b510c6d0c7f53328b3af2215bfdf6e66712c78b68101bf39b27`.

## Code validation and review rulings

Nine initial synthetic tests were watched fail before implementation and pass
after it. A single fresh read-only reviewer found three Important issues; no
Critical or Minor issue. One correction pass reproduced four new failures and
fixed exact-buffer authentication/full-context checks before target reads,
per-write immutable output hashes, and incremental gate/target-prefix evidence.
The independent checker now validates a retained failed prefix without reading
the unfinished target session. All13 targeted tests and the full1,463-test suite
passed. Another3,000 synthetic finite bit pairs agreed exactly across both
arithmetic implementations. No rereview or implementation agents.

Every behavior the reviewer declined to judge was ruled on explicitly:

- Actual controls/units/target coverage: root owned the frozen actual run and
  verification above; the cost of a failed source test is retained incomplete
  evidence and no missing-stock recovery.
- Upstream vintage and guard sufficiency: remain a conditional source hypothesis;
  even successful controls would not prove historical arrival or every upstream
  transform. A broader unverified inference could yield wrong reconstructed
  prices, so it cannot admit account inputs. This actual hypothesis failed.
- PIT/tradability, ST limits, actions, tax, account and returns: remain outside
  this source stage, with all admission flagsfalse. The cost is no qualifying
  physical return result until those obligations are independently satisfied.
- Publication/freeze/CI/artifacts: root owns exact remote and artifact checks;
  pending or failed CI must not be reported successful. Final run evidence is
  reported after publication.
- Full suite: root reran all1,463 tests; reviewer independently ran only the
  original9 relevant tests. The cost is that the full-suite result is not a
  second independently reproduced run. No deferred minors.

## Remaining work

SZ002326 still lacks an admitted raw/state/action packet; no conditional quote
recovery was permitted. The earlier SDK timeout and both failed HTTP attempts
remain intact. A different primary source or separately justified upstream
transform needs a new frozen source contract, not a relaxed version of this
failed test. Historical arrival, SZ002092's dated ST treatment, source action
coverage, literal tax alternatives and account dependencies remain unresolved.
The approved lawful fractional-share branch enumeration remains required if a
later admitted account reaches such an event; it cannot repair missing sources.
No strategy or2026 outcome was changed or selected in this stage.
