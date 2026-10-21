# Price-delay pre2026 replay: clock boundary repair

The frozen V1 development screen (`7256c37`) failed during its first descriptive-control replay at the final2025 bar. No case completed and there is no scoreable account return. Its code, plan, provider, partial output and full log remain preserved; the failure receipt binds the original log hash.

Qlib `TradeCalendarManager.get_step_time` reads calendar[index+1] to define a bar's right boundary. V1 had a physical daily quote calendar ending2025-12-31 and no future calendar, so Qlib fell back to that finite calendar and raised IndexError at its last entry. This is a runtime failure, not investment evidence.

The separately frozen repair creates a fresh copy of V1. Every existing file is copied byte for byte, then a separate `calendars/day_future.txt` contains the exact original2025 calendar prefix and the next actual session,2026-01-05, taken from the already registered source calendar. No weekday-generated holiday, price padding, shortened evaluation window or additional simulated session is permitted. V1 stays untouched.

All4010 quote binary files remain byte identical and capped at2025. The snapshot-facing `day.txt` still ends2025-12-31; its next-session price request fails. Only the backtest clock gains metadata to close the final2025 daily interval. This metadata extends into2026; it is explicitly not2026 market-value or outcome access. The actual installed Qlib now resolves all485 steps and the final interval2025-12-31 through2026-01-04 23:59:59 without an account run.

V2 account code and plan separately bind the future-calendar hash and check all4010 quote hashes. Before any completed outcome, the original24 formation receipts and all three target families must reproduce byte exactly. The single investment hypothesis,95% target, monthly schedule, prior-close sizing, two cost profiles, nonselectable controls and development selection rule are unchanged. A full behavioral suite and source-only preflight precede the frozen V2 replay.

This remains a reconstructed current-vintage, normalized daily-open engineering screen. It does not establish raw-share execution, minute-level feasibility, historical data arrival, OS isolation or the user's three-year return objective.
