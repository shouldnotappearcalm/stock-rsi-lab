# Chinese operating profitability: source contract

Build an independently named source measure motivated by the completed
cash-profitability field review. This is not a replacement for the unresolved
full cash-profitability measure or an exact Compustat/CSMAR replication.
The implementer chooses this bounded next step under standing direct-execution
authorization; no extra user approval is required for the already authorized
research, tests or push. No strategy rank or return is authorized by this step.

Contract `CN_OP_EX_RND_SAME_EDITION_LAGGED_ASSETS_V1`: current annual consolidated
revenue minus cost_of_sales, selling_expenses and administrative_expenses,
divided by the explicitly dated previous December31 total assets in the SAME
annual PDF. Research expenses must be separately, explicitly reported and are
retained as evidence; do not add them back or subtract them again. Preserve
negative monetary cells and negative numerators. No clipping, missing-to-zero,
annualization or winsorization. Normalize exact signed money in yuan/ten-thousand
yuan using Decimal with60-digit arithmetic. Assets must be strictly positive.

Keep both annual income columns and both balance columns with source lines,
physical pages, original units, header/date evidence and PDF identity. Compute
only the CURRENT fiscal-year measure: its comparison income column has no
same-edition two-year-lagged asset denominator. Do not borrow that denominator
from another filing. Generic/January1 opening columns do not establish the
required previous December31 balance. Reject unsupported tables, missing rows,
ambiguous headers/currencies, duplicates, extra numeric columns and cross-page
row continuations. Keep the existing parsers immutable; reuse their bounded
section/unit/header grammar in a separate module.

Records validate scope, date/column, normalized amount, literal/line integrity,
same-table metadata, exact field set and filing/capture chronology. Visibility
defaults to max(publication-day-end, actual observed capture). Conditional
publication-day-end reconstruction must be explicitly requested. Skip future
payloads before hashing/validation/computation. Visible source views preserve
all supported editions, not a latest-eligible strategy selection. Identical
duplicate records are idempotent; conflicting same-day editions fail closed.
Source coverage, unsupported latest reports and historical arrival remain
separate requirements; this module cannot choose an older favorable filing.

Implement one source module and one frozen two-document generator. Reuse the
original SH600166 fiscal2023/2024 PDFs and their source identities. Bind all
methods, this design/plan, raw-cell review, prior source-mapping review, original
PDFs and reviewed page evidence BEFORE new actual metric calculation. Commit,
push, verify the exact remote freeze, then execute once in a fresh local output
directory. Check every input/request before and after, including interruptions;
preserve original errors and never overwrite old outputs. The generator emits
two filing records, conditional/observed snapshots, input/output identities and
a summary; observed historical views must remain empty. Add a small versioned
real-row CI fixture only after successful source review, with no CI PDF fetch.

The next stage is a separately frozen historical-cohort coverage audit. No2026
financial/market data, stock ranks, portfolio returns, account edits or revised
failed experiments here. Investment admission and objective completion remain
false. Full objective still requires2024>0,2025>0,2026Jan-Oct>=10% on one frozen
continuous account; no source measure alone satisfies it.
