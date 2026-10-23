# Cash profitability source pilot: fields visible, full factor not admitted

The two-report source inspection is complete. It supplies evidence for an
explicit Chinese operating-profitability source fixture, but does not establish
a complete cash-profitability/accrual mapping. No factor value, ranking, trading
candidate or portfolio return was computed. The investment objective remains
unachieved; the previously rejected2026 asset-expansion result is unchanged.

## Frozen evidence and reproducibility

- Before additional financial extraction, source protocol/request/method were
  pushed as `4eeae056d77e0e979992c57fb091ab0cdc8d9141` and the remote head checked.
  Request SHA256: `5e1f5a44354793076d33992d32e151a019ccb4da0ab1c059e0b599878fb679c9`.
- Before note review, the bounded continuation was separately pushed as
  `02f36d00021068c992fa154bbfbc04a9b3d251b1`, again with the remote head checked.
  Request SHA256: `3effee86b99b3709c24361aedd0b6bf5f68c58ca4c87a9198cd9e75f110a1068`.
- Reused fixed-pilot issuer SH600166: fiscal2023 annual report, published2024-04-27,
  announcement1219874919,283 pages; fiscal2024 report, published2025-04-26,
  announcement1223327299,289 pages. No new issuer or2026 report was selected.
- All572 physical pages were text-preserved with pypdf6.10.0. pdfminer20251230
  independently extracted21 fixed statement/reclassification pages and24 bounded
  note pages. Eight new note-page renders were reviewed. Reader outputs are
  preserved separately; this is not a claim that every cell/page was audited.
- The first stage emitted595 files, the note stage41. All634 non-manifest output
  hashes and both request input sets were rechecked. Seven manually reviewed
  note pages additionally passed both-reader label/amount anchor checks.
  Raw source texts/renders remain local, not republished as a financial dataset.
- The public machine-readable [review](../../experiments/qlib/cash-profitability-two-report-source-mapping-review.json)
  is byte-identical to the local review; SHA256
  `7c8491c56432888997edc6c93e15c9e449678414d5afa8dc6105c75180951b18`.

The wrong-request-hash check refused execution before source parsing/output
creation. The full local suite passed1312 tests in19.876s before the source
freeze. That freeze's three CI jobs passed in
[run39900874192](https://github.com/shouldnotappearcalm/stock-rsi-lab/actions/runs/39900874192).
Documentation/JSON follow-ups still require their own exact-head CI status.

## What the accounting evidence changes

| Component | Original evidence | Consequence |
|---|---|---|
| Revenue/COGS/selling/admin/R&D | Consolidated income tables,2023 reportp108 and2024 reportp102; R&D is a separate row | A Chinese numerator can be explicitly defined from components. Do not automatically add separately reported R&D to it. |
| Income-tax payables |2023 p200;2024 p199 distinguish corporate income tax from VAT and other taxes | Total应交税费 is not the income-tax row required by the accrual formula. |
| Deferred revenue |2023 p204 and2024 p203 label递延收益 as政府补助;2024 p203 also lists warranty/telematics obligations under other noncurrent liabilities | Do not map递延收益 mechanically to operating customer deferred revenue. Contract/current/noncurrent obligations need a defined scope. |
| Accrued expenses |2023 p201 and2024 p200 separate预提费用 from deposits, engineering/equipment amounts, promotional amounts and other balances;2024 also has acquisition consideration | Total其他应付款 is not an established equivalent of accrued operating expenses. The named subrow does not prove complete operating coverage. |
| Debt and D&A |2024 p200 splits current loans/leases;2023 p217 separately reports depreciation and several amortization categories | A future contract must settle category coverage. A total or an arbitrary sum is not automatically a replication. |
| Source editions |2024 p156 explicitly offsets the2023 warranty reclassification between COGS and selling costs | Preserve both editions, matched columns and publication clocks. Do not combine an old COGS row with revised selling costs. |

The two most tempting shortcuts are therefore rejected on observed accounting
content, before any new strategy return: treating government-grant deferred
income as customer deferred revenue, and treating all other payables as accrued
operating expenses. This does not prove that a carefully defined Chinese cash
profitability measure is impossible.

## Original methods and remaining uncertainty

The [published Ball et al.2016 original](https://www.anderson.ucla.edu/documents/sites/about/clubs/asam/6-Accruals-cash-flows-and-operating-profitability.pdf)
was retrieved successfully from UCLA: PDF SHA256
`17ef06c9dcf658fa2ad1f22c784356883fd58f6de313e57d87cc0fe5f2d1e4c2`.
Physicalp17 defines monetary numerators before dividing by prior-year assets;
its R&D adjustment reverses a Compustat convention, and depreciation enters
balance-sheet accruals as a level. The earlier Dartmouth404/body remains archived.

The [PolyU manuscript](https://ira.lib.polyu.edu.hk/bitstream/10397/90052/1/PBFJ_Accrual_PolyU.pdf)
is also archived, SHA256
`bf7dbeb65c2820d670a1d5cccc0809c13787f7547ad684b53e4f9313199a75c3`.
Its cover dates this version2021-03-30, distinct from the2020 journal article.
Visual inspection confirms p12's lagged-assets table note conflicts with p15's
same-year wording; p15 also mixes an already scaledOP with monetary changes
and displays a change in depreciation. These are unresolved manuscript
implementation ambiguities, not findings about the final publisher appendix
or the authors' actual code. Chinese evidence is not interchangeable with the
U.S. findings or proof of long-only net profitability.

## Next bounded step

Propose a source-only contract for the transparent Chinese operating numerator
`revenue - cost_of_sales - selling_expenses - administrative_expenses`, keeping
R&D separate, and matching it to prior-year assets from the same edition.
This is an explicit research definition, not a claim of exact Compustat/CSMAR
replication. Freeze that contract and fixtures before computing it; do not
silently replace the full cash-based measure with this simpler one.

Only after source validation should coverage be audited on the existing fixed
historical cohort, retaining unsupported/newer reports. No economic cutoffs,
rank direction, formation schedule or target names have been selected here.
Any candidate must subsequently freeze those choices before2024/2025 development
and retain the previously exposed status of2026. Missing observed historical
arrival remains unresolved; reconstructed publication-day-end visibility is
conditional. Neither this pilot nor a published anomaly meets the frozen
2024-positive/2025-positive/2026Jan-Oct-at-least10% account requirement.
