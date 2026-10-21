# Source grammar V2:8 reports supported, whole-universe investment data incomplete

The frozen V2 completed on the same36 original annual reports from12 issuers.
Supported source parses increased from3 to8, producing16 fiscal-column records.
The original three successful reports retain all18 original cells and evidence.
There are19 unsupported schemas and9 unverified identities. All36 cases remain;
this is a source feasibility improvement, not a stock-selection or return result.
Required2024>0,2025>0 and2026January–October>=10% remain unproven.

## Freeze and actual execution

Code, source grammar, sparse real-source fixture and tests were pushed at`761ba57`
before the full source run. Request SHA256:
`e57cd393d7b9e3ae44f7ba681d34cb984f86ce8104c3f80b0035ed41dc75a6c0`.
The original narrow parser, raw PDFs, earlier source outputs and failed strategy
accounts were not modified. No new source network, price/return query or2026
financial/market values were used.

The actual run exited0. All336 inputs including the request rehashed unchanged;
41 new immutable outputs contain36 case packets, aggregate cases, input-before/
postcheck, terminal and summary. Every one of the36 full-page text-hash inventories
matches the earlier source run. The fixed sample remains a source sample, not an
investment universe. Its historical membership origin does not prove historical
nonfinancial/accounting classification or complete investment-source coverage.

| Classification | Original | V2 |
| --- | ---: | ---: |
| Supported, pending full visual/accounting review |3|8|
| Unsupported schema/fields/unit evidence |15|19|
| Unverified issuer/title identity |18|9|

Newly supported: SH603517 FY2022/FY2024 and SH600418 FY2022/FY2023/FY2024.
SH600166 retains its original FY2022/FY2023/FY2024 support. Thus only two issuers
have all three annual reports supported; one additional issuer has two reports.

All19 schema failures remain explicit:10 lack V2's narrowly scoped same-page
currency evidence,8 fail unique ordered statement boundaries, and1 lacks literal
revenue. These are parser/source-contract failures, not evidence of zero amounts
or necessarily defective underlying reports. Financial proxies were not used.

Identity behavior is not a monotone improvement for every source. SH600655's
three reports previously matched a cover code but now become unverified because
other listed securities codes appear within the first20pages (SH600702/SH603919).
V2 preserves these literal conflicts. It does not prove the PDF belongs to the
wrong issuer: the overly broad identity context needs a separate revision that
distinguishes the report's issuer from other companies it describes. No original
supported parse was lost, and these transitions are retained in the full result.

## Separate original-page check

[Source-cell checker](../../experiments/qlib/audit_sources/2026-10-22-profitability-v2-source-cells.py)
imports no production modules and directly re-extracts original PDF pages. It
checks all48 current/comparative amount cells from the eight supported reports,
their exact row location inside consolidated rather than parent boundaries,
fiscal column index, original literal CNY unit/header, PDF/page/row/record hashes,
and source/publication/capture identities. `Fraction` independently checks exact
unit normalization. All18 old successful cells retain every original field.

The actual check passed; report SHA256:
`1b1c6863d14b3082f8af32633948ad7a0a333b6d5aac89c310deecdf213ac6fe`.
It also checks all336 frozen inputs and41 outputs before/after. This is a separate
implementation by the same researcher after the run, sharing pypdf6.10.0. It is
not blinded, an independent-researcher audit, a complete manual review or proof
of financial-version history/economic comparability.

Four counterfactuals on temporary copies all fail at semantic checks even after
updating the record digest and both case packets: incorrect normalized amount,
incorrect fiscal column index, asset provenance outside the consolidated range,
and backdated capture time. None emits a success report. All41 original outputs
remain unchanged. These checks require local original sources and are distinct
from CI's public sparse excerpts.

## Regression, CI and next work

Full local suite passed985 tests. The13 added V2 regressions include original
real-row numeric preservation, new real multiline/note excerpts, explicit local
currency, missing/proxy/extra-column rejection, duplicate/missing table boundaries,
bounded/conflicting code identity, original visibility behavior, future payload
isolation and interrupted execution preserving original exception/posthashes.
The first test command accidentally used system Python3.9, which cannot import
this Python3.11+ project; the declared research Python3.11 run passed. One new
test initially expected a page21 code to influence a20-page window; its assertion
was corrected before freeze to match the stated bound. The full source run was
started only after the final985-test pass and freeze push.

The freeze CI [39660229906](https://github.com/shouldnotappearcalm/stock-rsi-lab/actions/runs/39660229906)
passed all three jobs (Python3.11, Python3.12, research dependencies). Check the
results push independently; this earlier run certifies only its frozen code.

Next data work must separately scope issuer identity to cover/company information,
prove currency inheritance from actual financial-section structure, and resolve
repeated statement sets without choosing favourable numeric rows. Keep V2 outputs
and missing financial fields intact. Broader historical nonfinancial universe,
original annual/correction coverage and accounting compatibility remain necessary
before registering one gross-profitability strategy and2024/2025 controls. The
same unchanged passing candidate can then receive a separately frozen2026 test.
Actual2026 capture cannot certify observed2024/2025 arrival; date-end publication
reconstruction remains explicit and conditional. October2026 is still incomplete.

Evidence: [full V2 result](../../experiments/qlib/profitability-fixed12-v2-results.json),
[source-cell check](../../experiments/qlib/profitability-fixed12-v2-source-cell-audit.json),
[counterfactual checks](../../experiments/qlib/profitability-fixed12-v2-source-counterfactuals.json),
[frozen plan](profitability-fixed12-v2-plan-2026-10-22.md).
