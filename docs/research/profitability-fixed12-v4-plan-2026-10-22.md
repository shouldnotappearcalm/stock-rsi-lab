# V4 source boundary repair after rejected V3 full run

The investment objective is unchanged:2024>0,2025>0,2026January–October>=10%, one
frozen strategy and continuous account, with no2026 method feedback. This is a
source-format repair, not a portfolio test or a new financial proxy.

V3 freeze`566278a` passed999 tests and its CI. Its actual full36 run then failed
the required old-success guard: `old supported report lost:
SH603517-2022-1216709701`. All36 cases were classified;395 inputs rehashed unchanged;
40 outputs retain original failure/terminal/journals/cases; no successful summary
exists. The12 parsed cases are not an admitted run. Preserve the complete failure
in `profitability-fixed12-v3-failure-record.json` and local originals.

Root cause is directly reproduced by original physicalpage84: the text extractor
places printed page number84 immediately before the unnumbered income title. V3
joined those strings as though84 were an enumeration prefix, swallowing a valid
title. The old sparse fixture omitted the page-number prefix and missed this
case. A new genuine-prefix fixture reproduces V3 rejection and V4 preservation.

V4 changes only this joining rule: a standalone numeric prefix must be followed
by a literal enumeration separator before an exact title, or already end with
that separator. Naked page number + unnumbered title remain separate lines. Join
neither across physical pages. Keep all V3 identity/currency/section/header/row
bounds, explicit RMB evidence, three fields, rejection rules and Jan1 opening-
balance isolation. Keep all old/V2/V3 source/method files immutable. New module
is`annual_profitability_v4.py`; runner is`inspect_profitability_fixed12_v4.py`.

Before rerun freeze and push`profitability-fixed12-v4-request.json`, binding the
complete prior dependency chain, all40 failed V3 outputs, failure record, new
regressions, source prefix and this plan. Verify exact failed terminal and the
absence of a V3 success summary before any extraction. Use one new fresh output
directory`gross-profitability-fixed12-source-context-v4-20261022`; no overwrite or
resume. Same36 reports, pypdf6.10.0,1200-page cap, no new network/market/returns.

Run full tests first. New tests cover the real numeric-page-prefix failure,
literal separator and same-page bounds, unchanged V3 current-only/date behavior,
classification/visibility flags and interrupted execution. After all36 source
cases, require preservation of every supported V2 fiscal cell/coordinate and all
V3 parsed-case cells; an error stops with full original failure/posthash evidence.
Retain all36 statuses and transitions, current-only opening-date cases, page text
hashes and journals. No successful summary on regression or changed input.

Source coverage is still distinct from historical nonfinancial/accounting
compatibility, financial version history, actual arrival and factor admission.
All remain false. The fixed12 source sample cannot become an investment universe.
Broader candidate source coverage must use authenticated pre2026 membership and
explicit missingness, not successful parsers or2026 returns to pick stocks.
Reconstructed publication-day-end availability remains conditional. No goal
completion or qualifying-strategy claim follows from this repair.
