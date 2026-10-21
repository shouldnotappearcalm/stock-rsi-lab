# Fixed value/momentum composite: raw-share daily development results

The fixed composite passes its predeclared **pre-2026 physical-share daily-proxy gate**, using the higher 40bp cost profile. It has not passed minute-execution qualification, and no 2026 return for this candidate has been computed.

Same 24 targets and 103-name union, continuous CNY 1,000,000 account from the 2023-12-29 baseline through 2025-12-31, without annual resets or control replacement. Source/account methods and profiles were pushed in `b7e5868` before actual account outcomes; the independently reconstructed source projection was pushed in `87a20ae` before the account ran. All original strategy, allocator, account, source files and previous failures remain unchanged.

| Extra cost per side | 2024 net | 2025 net | Mean actual exposure | Maximum drawdown |
| --- | ---: | ---: | ---: | ---: |
| 20bp | +6.242551% | +29.205416% | 94.029086% | -22.088313% |
| **40bp reference** | **+4.902274%** | **+27.549335%** | **94.108320%** | **-22.377849%** |

Costs include original buy 5bp/sell 15bp and CNY 5 minimum, plus separately rounded extra cost at each fill. The unchanged account reserves a flat 20% of cash dividends; this is not actual FIFO tax settlement. At 40bp, ending equity is CNY 1,338,021.53, total fees CNY 65,784.76, gross dividends CNY 50,354.11 and cash-tax stress reserve CNY 10,070.82. CNY 1,000,000 is a research assumption, not user-selected deployment capital.

Both accounts reconcile all 486 source sessions and 485 investment sessions, 24 decisions/snapshots each, and record/ex-date ownership for all 255 events. The 20bp case has 704 orders/690 fills; 40bp has 701 orders/689 fills. All fills use integer shares, buys obey 100-share units, source halts and market constraints retain unfilled behavior, and cash/share flows and held valuations reconcile. All 60 missing prelisting sessions are justified by the primary listing boundary with no required inventory/order/decision price; no synthetic bars or factor-derived entitlements were introduced.

The standalone stdlib ledger auditor uses a separate arithmetic implementation: it reconstructs fees, FIFO saleable lots, corporate claims and payments, ownership, NAV, annual returns, order IDs/statuses, all 48 prior-close allocations, and all 48 visible snapshots from original sources and frozen targets. Root authored the separate algorithm; the reviewing agent independently executes and reviews it. Its six semantic account mutations are rejected without relying on artifact-file hash mismatch. The independent source auditor additionally reconstructs all 255 event IDs/receipts and rejects 14 source mutations. Full regression before the actual run: 493 tests passed.

## Next source requirement, not execution admission

A read-only inventory covers the entire cumulative target prefix, rather than just the orders that happened to fill in the daily proxy. This protects against different ownership paths under intraday execution. It requires 1,744 active stock/session minute packets and explicitly records two halted intervals. Eight fixed earlier caches provide 1,051 matching packets; 693 are uncached in those eight sources. All 2,225 matching cache references authenticate, with zero response conflicts. Existing packets pass reconstructed close/range/volume checks; no new network calls or 2026 market-value reads were made by this inventory.

The next phase must freeze and capture the 693 missing identities, independently admit complete minute data, then test the existing registered 1%/5%/10% participation scenarios with the same two cost profiles and fixed account. All three 40bp participation cases must satisfy the pre-2026 qualification; picking a favorable participation case is not allowed. Only then may a separately frozen 2026 diagnostic proceed.

The five-minute sampled-price model, 9.5% daily reference protection, source reconstruction, four inherited event-specific capital-tax inferences and publication/signature caveat do not establish exact historical arrival, all corporate actions, official price-limit history, queue/impact or live-trading performance. No original statutory-tax or source-certification flag has been upgraded. The user's 2026 Jan–October >=10% requirement remains unproven; full October is not yet complete, and prior consumed diagnostics cannot become sealed evidence.
