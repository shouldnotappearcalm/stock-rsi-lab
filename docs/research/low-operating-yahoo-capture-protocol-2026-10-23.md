# Bounded Yahoo opaque acquisition after strict Tencent volume rejection

Previous turn made progress: f53ad2b retained640source rows/154earlier quarantine,
486 allowed sessions,1944exact OHLC cells,34exact volume rows,zero target preparation.
The strict gate and every earlier failure stay unchanged. The full requirement is
one continuous account with2024>0,2025>0,2026Jan–Oct>=10%; not achieved.

AKShare official stock_zh_a_hist_tx documentation describes units, not a provider
rounding rule. Do not introduce tolerance inferred from observed volume differences.
The alternative lead is Yahoo chart history, using inspected yfinance const.py
blob c933a68abe4db8b78ac4040aa4e132b6700918d4 and history.py blob
af5f6d82b3044ab90e828e58e6d03bde69c05982. Their exact locally retained bytes are
bound. This is acquisition with installed curl, not an implementation feature.
Do not execute yfinance's auto_adjust/repair/cookie/current-info wrapper.

Freeze two exact GET argument arrays: SH600118 control then SZ002326 missing code.
Request daily timestamps for2023-12-29inclusive..2026-01-01exclusive, based on
Asia/Shanghai midnight. No current endpoint, retries, redirects, TLS bypass,
credentials, installation or background work. Each gets one durable reservation,
20second total/10second connection/1MiB cap. -q disables implicit curl config.
Cancellation or persistence failure stops further requests; ordinary transport
failure retains available bytes and does not consume the second resource budget.
Publish and verify remote freeze before either request. Verify all inherited
source/input identities and every output before and after terminal persistence.

Raw bodies and headers stay local and opaque, including any attached current
metadata or split/adjusted values. This stage does not decode date/price/volume,
accept a source, calculate a return or alter the fixed candidate/43names/24targets/
95%weights/costs. At most HTTP status, sizes, transport diagnostics and hashes are
published. Successful HTTP is not quote or account admission. A later separately
frozen selective decoder must validate dates and ascertain split semantics,
exact-cent/volume agreement and required state/actions before any account use.
No2026 source values are decoded or used for selection.2026already exposed stays
exposed. This exact new source budget preserves every previous failed attempt.
