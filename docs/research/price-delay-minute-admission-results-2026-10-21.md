# Price-delay minute-source verdict

The strict pre-2026 minute-source admission failed. It admitted 2,490 ordinary
stock/session packets and rejected 12 SZ002092 packets because the unchanged
daily source marks those sessions ST. All rejected packets, reasons and original
source bytes remain preserved. The run exited with code 2; reconstructed
execution admission remains false. No new account replay or 2026 candidate
return was computed.

Capture and source validity are separate. The complete 2,502-packet capture,
including 1,584 original-byte copies and 918 fresh response chains, passed an
independent technical reconstruction. An independent admission audit then
reproduced the full failed summary and all 2,502 details, including 119,520
five-minute windows for the 2,490 ordinary samples. Root reproduction was
byte-identical. Nine semantic negative controls were rejected.

SZ002092 appears only in the original 2024-01-02 target, while its original
daily data starts the ST interval on 2024-05-21. Absence from a later target
does not prove absence from actual holdings or pending orders. The next
source-scope experiment must establish those dependencies separately in every
account; it may not relabel ST samples ordinary, erase this failure or alter
the investment rule. See the separately versioned ordinary-source guard plan.

The earlier 40 bp daily proxy remains a pre-2026 engineering result:
2024 +15.670055%, 2025 +4.107628%, mean exposure 92.134256%. Those results do
not establish minute execution or the user's 2026 January–October >=10% goal.
