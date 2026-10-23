#400 original annual covers and total-assets extraction,without2026 ranks

The completed394-issuer metadata source and all400 original PDFs passed separate
source-byte QA. Keep their exact identities,all editions,publication dates and
actual observed capture timestamps. The source cutoff remains2026Oct21;the
strategy,source cohort,industry labels,freshness,decile/weight rules,capital and
costs remain unchanged. This stage admits no2026 portfolio outcome.

Add`scripts/inspect_asset_expansion_2026_assets.py` with pure`inspect_pages`
and bounded original-PDF workers. Reuse unchanged
`annual_profitability_v7.document_identity`,`annual_assets.parse_balance_only`
and`annual_assets.make_report`,including their complete existing parser chain.
Do not edit old parsers,requests or source outputs to fit2026 documents.

Decode each original once with installedpypdf6.10.0 on the pinned Pythonruntime,
at most1200 physical pages per PDF andfour outstanding documents/four process
workers. No agent subprocess,network,package install or account replay occurs.
Hash the original PDF before/after each worker. Persist complete physical page
text caches and every page hash,including failed cover/table cases. A source
PDF extraction error is retained with no fabricated text/cells. An unexpected
worker/runtime/persistence error stops the run with completed/submitted/pending
identities,original exception and complete input posthashes. Never overwrite
or automatically resume this run.

Require literal issuer/annual-year cover identity using the existing first5/
first20-page rules before numeric cell interpretation. A metadata year remains
unverified until the cover matches. If a future yearless metadata candidate is
present,resolve only an unambiguous literal annual title on the firstfive
pages;never infer publication-year minus1. Contradictions/ambiguities stay
unverified and produce no asset report.

Extract only consolidated total assets from the original primary financial
section. Income titles may establish structure;income values are not factors.
Keep exact literal/unit/CNY amounts,current/priorDecember31 identities and
same-edition provenance. Current-only/January1/undated opening columns stay
current-only,not an invented prior year-end. Reuse the same archivedCAS19
currency reference and bind its original body/text/receipt files. Positive
cells passing the unchanged source grammar remain pending separate sourceQA,
not investment-admitted. Retain all schema failures without old-report fallback.

Freeze/push the400-document list,full PDF-byte audit closure,parser/runtime/
currency-reference/test hashes and this plan before any original PDF text or
numeric extraction. Source-only summary reports cover/table statuses,cell/
paired-column counts and visibility. DefaultOBSERVED mode must still showzero
reports before their actualOct23 arrivals;explicit reconstructed publication-
day-end mode may expose eligible editions,but is not historical-feed proof.
Neither mode selects investment ranks here.

After execution,independently inspect original PDF source cells using a
separate extractor/checker,including units,headers,physical pages and any
currency inference. Bind every supported cell and retained failure. Only then
prepare per-formation source views and2026 factor/rank/account execution under
the already frozen policy. Full2024>0,2025>0,2026Jan–Oct>=10% is still required;
globally exposed2026 outcomes must not drive a rule change or a holdout claim.
