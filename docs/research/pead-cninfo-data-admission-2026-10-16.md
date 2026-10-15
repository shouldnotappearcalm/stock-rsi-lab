# A-share earnings-announcement factor: data admission before any return search

The next economic hypothesis comes from published A-share [post-earnings-announcement drift research](https://www.sciencedirect.com/science/article/abs/pii/S1057521924003922): the opening response after an earnings announcement can proxy for earnings surprise, and price adjustment may continue afterward. The paper reports a strategy result under its own universe, attention measure and trading rules. That number is **not** a return forecast or reproduction for this project. This candidate is different from trying another model on the same Alpha158 price features.

The data pilot used the official [CNINFO announcement query](https://www.cninfo.com.cn/new/hisAnnouncement/query), following the request schema in [AKShare's implementation](https://github.com/akfamily/akshare/blob/main/akshare/stock_feature/stock_disclosure_cninfo.py). Twelve main-board CSI500 stocks were selected by a fixed hash from the membership intervals active on 2024-01-02: six Shanghai and six Shenzhen stocks. The [script](../../scripts/audit_cninfo_report_admission.py) queried annual, Q1, half-year and Q3 report categories for publication dates in 2024–2025, with a bounded full-text fallback where a category was empty. Raw announcement metadata stayed in ignored local storage; the [admission manifest](../../experiments/qlib/cninfo-report-admission-2026-10-16.json) records counts and its hash.

| Admission check | Observed |
| --- | ---: |
| Fixed sample | 12 stocks |
| Required original reports | 4 types × 2 publication years × 12 = 96 |
| Category-only complete stocks | 11/12 |
| Complete after full-text fallback | 12/12 |
| Report-event prior close / next open price pairs in Qlib | 96/96 finite |
| Supplement/correction example | 000001, 2023 annual report supplement published 2024-12-07 |
| CNINFO timestamps | All 143 category rows report 00:00 |

The missing category case was 000750's 2024 Q1 report: full-text search returned it with announcement ID `1219912916`, while the Q1 category did not. This makes a category-only bulk pull unsuitable. The midnight time is also **not a verified publication hour**. The safe availability convention for a later event factor is the end of the displayed announcement date; observe the next trading session's opening response only after that open, then wait for the following legal execution in the replay. The original report, summary, visual version and later supplement must remain separate events. The current CNINFO organization lookup covered all 501 CSI500 membership intervals checked at the sample date, but it is current metadata, not a historical security master.

This pilot tested data coverage and price-pair availability, **not the direction or profitability of the signal**. A full-universe candidate would need all historical constituents, bounded pagination, fallback coverage, deduplication by announcement ID, conservative date-to-wake mapping, and a registered holding/portfolio rule before any development return is opened. The 2026 diagnostic interval stays unavailable for candidate selection. The already reused 2024–2025 interval would still be development evidence only.
