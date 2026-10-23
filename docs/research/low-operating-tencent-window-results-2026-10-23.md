# Tencent window experiment: strict volume gate rejected

Frozen commit `da1885e11b65b87e685c13e6c3a22f39f6ad1901` was pushed and its exact
remote SHA verified before this experiment. Request SHA
`c0b423f50eda80014c78de2c2ec1e0ade84747939180af06c32e8ca6f69d104b`.
One run, no retries, network, parameter changes, accounts or new return calculation.

The SH600118 response contains 640 source rows. Date/hash-only
quarantine retained 154 earlier records without reading their
numeric fields; 486 unchanged rows cover all486 explicit sessions
2023-12-29..2025-12-31. All1944 OHLC cells exactly match the original control.
Only34/486 volume-share cells match;452 differ. All486 amount values were compared,
none exactly match; amount remains a separate unadmitted diagnostic. These facts
do not establish a rounding law or authorize changing the strict source gate.

The frozen price-plus-volume gate is False. Target preparation and numeric decode
were never invoked:0 SZ002326 rows. Component completeness isFalse. Earlier
rejected date-only/float32/transport traces remain unchanged. No2026 quote values,
portfolio return, historical arrival, state/action/tax or account admission follows.
The full2024>0/2025>0/2026Jan–Oct>=10% objective remains unachieved.

The checker independently reconstructed component values/control comparison but
shares date-window selection, slice walker and authentication/orchestration. Root
rehashing verified 633 inputs and491 output artifacts;
490 selected historical JSON artifacts are public. Original/prepared raw
buffers stay local; their hashes remain in the proof. No independent full parser
or window-boundary correctness claim is made.

One fresh whole-change review found2Important defects. One RED-to-GREEN correction
pass added5 failing regression cases across2tests: independent control validation
now precedes every target preparation, and impossible target lifecycle states are
rejected.27related tests and1490full-suite tests passed. No rereview was performed.
Deferred inherited minors: ignored-string UTF-8 validation and the65-empty-container
depth edge; bounded slicing does not claim full JSON validation. Catchable native
interruptions are covered; uncatchable termination/storage failure is excluded.

Next source work must separately document provider volume/amount precision or find
an exact source; it must not silently relax this frozen request or alter the
strategy using exposed2026 outcomes. Original target/state/action/arrival/account
requirements still apply even if a later component source passes.
