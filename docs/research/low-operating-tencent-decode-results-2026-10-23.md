# Selective Tencent decode: rejected an earlier-than-requested first row

The frozen decode did not admit a quote row. SH600118's historical array has640
rows and its first date is2023-05-17, earlier than the requested2023-12-29 start.
The frozen method requires every selected row to belong to the486 explicit
2023-12-29..2025-12-31 sessions. It stopped at control row0 before decoding that
row's numeric values. SZ002326's decoder was never invoked. This identifies a
response-window compatibility issue, not a strategy return or proof that later
rows are unusable. Neither endpoint's remaining date range has been inferred.

## Freeze and actual evidence

Request SHA256
`fcff9c5abee242a9e5115e36f62372768636d3a45ed8b409786aaa7d2d2297d7`
binds623 original/source/method/spec/plan/review files. Commit
`13a2ccffb096e0c3be3bf0b37a6eb8389059912e` was pushed and matched with
git ls-remote before the actual decode. No new network request was made.

The single run raised ValueError `date outside frozen explicit sessions` and
retained a failure terminal: CONTROL, failed index0,0 completed control rows,
0 target rows, control gatefalse and target decoderfalse. No earlier rows were
silently skipped, no price was rounded, and the date window was not widened.
The original opaque responses and every prior SDK/HTTP/f32 failure remain.

The separate component checker authenticated the frozen input graph and empty
persisted prefix; its PASS means faithful failure receipts, not source validity.
It intentionally did not continue the failed row. Root separately re-examined
the already rejected date0 and structural row count using the bound slice walker,
without reading numeric quote values. Root rehashed all624 inputs including the
new request and the sole captured terminal; public copies are byte identical.
The checker shares the slice boundary, so this is not an independent JSON parser
or a validation of every ignored/remaining response value.

Historical arrival, ST/suspension, actions, tax, account admission and returns
remain unverified. No new2026quote/outcome was decoded or used in this stage;
2026remains previously exposed and is not a sealed test. The goal remains
2024>0,2025>0,2026Jan–Oct>=10%, unachieved; source-code/test progress is not a
qualifying investment result.

## Software verification and dispositions

Eleven initial/precision tests were watched fail and pass. A single fresh
read-only review found five Important issues, zero Critical and two Minor.
One correction pass added five further tests and empty-prefix coverage, watched
failures first, then passed all16 targeted tests and the full1,479-test suite.
Another1,500 synthetic nested/escaped/unicode selector cases agreed with the
standard JSON oracle. No rereview or implementation agents.

The five fixes recheck the full context after target marker persistence and
target buffer loading; trap inexact/underflowing unit conversion; reconcile
durable rows on interruption; validate existing markers/aggregates independently
of overall success; and verify terminal bytes/context after atomic publication.
The prior frozen finalizer is unchanged. A new finalizer preserves rejected
terminal bytes and avoids rewriting inherited source identities.

Explicit rulings and costs, in decision order:

- Amount exact agreement remains separate from the OHLCV gate because this frozen
  policy does not execute from daily amount. No tolerance/full admission follows;
  cost: conditional quotes may still be insufficient for later account/factor work.
- Use a new finalizer while preserving the old dependency bytes. Cost: narrow
  publication logic is duplicated; unrelated inherited workflows remain unchanged.
- Real contents/coverage/control/units belong to root's frozen actual run. Cost:
  failed evidence stays incomplete and does not recover target quotes.
- Source identity beyond byte bindings and historical capture provenance remain
  conditional. Cost: cross-provider agreement would not establish arrival/vintage.
- Publication, exact remote, receipts and finalCI are root-owned and verified
  separately. Cost: unverified/pending/failed publication cannot count as success.
- Root reruns the full suite; reviewer independently ran only11 committed tests.
  Cost: the review did not independently reproduce the whole suite.
- Accounts/actions/tax/arrival/returns/2026goal require later separately frozen
  work. Cost: component success alone cannot produce a qualifying return claim.
- No destructive power-loss/SIGKILL tests or OS locking guarantee. Cost: no
  durability promise after uncatchable termination or arbitrary later mutation;
  deterministic catchable windows are covered.
- Other inherited behavior is outside this review; only exercised dependency
  paths were inspected/tested. Cost: no retroactive audit or repair of legacy flows.

Deferred minors: ignored strings are not fully UTF-8 validated, and65empty nested
containers pass the intended64container cap. Selected strings and1MiB response
limit remain checked. These cases retain documented limited guarantees.

## Next source question

The response includes earlier history despite explicit request dates. A new
source-window adapter can be proposed that inspects dates only, quarantines a
strictly earlier prefix without decoding its quote values, rejects later/future
rows, and feeds only exact allowed sessions into this unchanged strict decoder.
That requires a new frozen contract/control run, preserving this failure. It
changes ingestion semantics, not candidate tickers, factors, weights, dates,
costs or the three-period investment gate. The remaining rows' validity is still
unknown; no source filtering or recovery has been executed in this experiment.
