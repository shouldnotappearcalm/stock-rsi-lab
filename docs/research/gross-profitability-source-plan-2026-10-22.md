# Gross-profitability financial-vintage source pilot

The investment objective stays2024>0,2025>0,2026January–October>=10%. The last
monthly risk-overlay trial failed2024 profitability. Its methods, accounts,
sources and failures stay unchanged. This new work builds the missing financial
input for a separately motivated profitability hypothesis; it registers no
strategy or return claim at this stage.

## Mechanism and source decision

Novy-Marx's2013 published paper defines profitability using gross profit divided
by book total assets. The original PDF's pages1/3 were read and rendered. Gross
profit uses revenue less cost of goods sold; it is not net income or total
operating expenses. The source-level Chinese mapping here uses consolidated
营业收入 minus 营业成本 over consolidated 资产总计. Accounting definitions need
wider cross-firm verification before an investment test. The original paper's
sample, nonfinancial scope and timing are not reproduced by this one-issuer
pilot. No published return is treated as a prediction for2024–2026.

Sources: original paper DOI10.1016/j.jfineco.2013.01.003; published-paper PDF from
https://oldschoolvalue-files.s3.amazonaws.com/pdf/Novy-Marx_Gross-Profitability-Anomaly_JFE_2013.pdf
(identity corroborated by the author's Rochester bibliography and NBERw15940
abstract). Paper pages1/3 were checked, not the whole empirical study. Sloan1996
was also inspected for field requirements; its full balance-sheet accrual inputs
are absent from existing data. No accrual strategy is registered or relabelled.

## Fixed data scope

Reuse the two immutable SH600166 PDFs already captured onOctober17,2026 under
`fundamental-first-issuer-primary-doc-request.json`. This issuer was selected
previously as the first name in a fixed-hash12issuer source pilot; selection
uses no price, factor rank or strategy return. Documents are the2023 annual
report published2024April27 (1219874919) and2024 annual report published2025April26
(1223327299). New source review records original hashes, literal scalar cells,
20 paper/report render/text artifacts and limitations. Original PDFs are neither
replaced nor redistributed in the public repository.

Extract current and comparative columns separately: four observations across
three financial periods. Physical pages104/105/108 of2023 report and98/99/102/156
of2024 report were visually checked. Each numeric cell records unit, column,
row, physical page, table header and original document identity. Parent-only
statements, total operating cost, third numeric columns, unknown units/currency,
missing fields, invalid values and ambiguous duplicate rows/tables fail closed.
The deliberately bounded parser supports only this explicit two-column schema;
it is not a general annual-report parser or full-sector accounting taxonomy.

The2024 report reclassifies2023 warranty-related selling expense into cost of
sales. The comparative cost differs from the original2023 report byCNY285157511.48.
Both versions must survive. Presentation changes affect economic comparability;
a temporally correct input alone does not make all profitability ratios across
firms or years comparable. These two files do not prove the first public date of
the revision or completeness of all other corrections/interim disclosures.

## Visibility contract

`src/stock_rsi/annual_profitability.py` retains one coherent set of consolidated
cells per document/fiscal column. Within this two-document subset, the latest
visible publication for an issuer/period wins; conflicting same-day documents
are ambiguous and rejected. No cross-version mixing of statement cells.

Default `OBSERVED` visibility requires both conservative public-day end and the
actual2026 capture timestamp to have passed. Therefore it admits no historical
2024/2025 observation. Explicit `RECONSTRUCTED_PUBLICATION_DAY_END` mode permits
conditional snapshots only after the stated public day's23:59:59.999999Shanghai.
It is a reconstruction assumption, never a claimed measured historical arrival.
As-of queries may be on closed days for analysis; they create no trading session
or order. No future payload is hashed/validated/scored before metadata admits it.
Later comparative revisions cannot change an earlier snapshot. Only the subset
of disclosed documents is represented; all historical revisions remain uncertified.

## Frozen generation and checks

`scripts/build_gross_profitability_source_fixture.py` authenticates a fixed
request, five methods, original capture metadata/PDFs, manual reviewed cells,
paper and20 derived evidence artifacts. Freeze and push
`experiments/qlib/gross-profitability-source-request.json` before real fixture
creation. Runtime PDF extractor is already installed pypdf6.10.0; no install,
market query, price read, stock ranking, account or return scorer is allowed.
Source values and accounting reclassification have been inspected for data
feasibility before this freeze; this is not a claim they were unseen.

The output directory must not exist. Seven immutable outputs: observations,
snapshots, page_text_sha256, input-before, input-postcheck, terminal, summary.
The runner parses the original PDFs, matches12 literal amounts to the prior
visual review, and emits16 historical queries in observed/reconstructed modes.
Default observed queries must all be empty; the2024 year-end reconstructed
snapshot must be unchanged when the later document is added. Every frozen
input and the request are rehashed afterward, even on interruption, preserving
the original exception and terminal evidence. No successful summary after input
mutation or terminal-write failure.

Behavior regressions cover source table/column/unit/decimal guards, negative
gross-profit retention, publication-day boundary, observed-vs-reconstructed
availability, same-day ambiguity, later restatement/future-payload independence,
source omission/mutation, future/ranking/ROI permission changes and interrupted
PDF extraction. Run `PYTHONPATH=src python -m unittest discover -s tests -v`.

## Required next stages toward the actual objective

First verify this source fixture and raw/manual-cell agreement. Then extend
original filing metadata, initial2022 originals and accounting compatibility to
the preexisting12issuer source sample under a separate bounded capture request.
This sample is not an investment universe. Before ranking or returns, require
historical constituent and nonfinancial identities, sufficient whole-universe
source coverage, and original/corrected versions at each formation.

Only after source feasibility, separately register one profitability candidate's
full investment hypothesis, lag, long-only rule, budget, comparison/control,
2024–2025 selection and physical-account gate. Passing those precedes a frozen
2026 diagnostic. No thresholds, tickers or methodology are selected from2026
outcomes. This phase neither narrows nor satisfies the three-period objective.
