# Unchanged IVOL horizon: clock admission failed before quote decoding

The frozen method at `7b23e732c87f863fa71f69766d7a15309c146316` was pushed
before the actual application. The request SHA is
`c5cdfdb602d7d233a374a08eefeebdefa3cec6b6a0890b27a57b22e63ff84301`.
The process exited 2 with `UNCHANGED_IVOL_CLOCK_ADMISSION_FAILED`.

All 34 monthly boundaries were checked against the authenticated explicit
provider calendar. The sole denial is the 2026-03-02 formation: its preceding
natural month ends on 2026-02-27 and contains 14 source sessions, below the
unchanged minimum of 15. A complete short month is not repaired by manufacturing
an extra observation. No skip, carry, alternative lookback, threshold change,
or neutral target was introduced.

This is an operational failure to apply the frozen specification throughout
the requested horizon. It provides no evidence about 2026 investment profit
or loss. The full-provider snapshot and factor were not invoked by the denial
branch; no new 2026 quote values, targets, orders or portfolio returns were
produced. This statement rests on the reviewed control flow and denial-branch
regressions, not OS-level future isolation.

All 5,356 bound inputs passed postchecks, including the prior source evidence,
the completed 26 account outputs, the old failed run and original financial
artifacts. The separately established pre2026 engineering result remains
2024 +22.322729%, 2025 +8.4703375% for the 40bp reference profile. Those returns
are continuous raw-daily proxy account results, with the previously reported
PIT, tax and execution limitations; they do not fulfill the three-period goal.

The full-provider price calendar ends on October13, and the unconditional
interim observation end remains October20. October is incomplete; this run
does not calculate even an interim 2026 return. The project has prior 2026
exposure and makes no sealed-holdout claim.

Local and clean-CI-environment regression suites each passed 784 tests (three
optional Qlib skips in the latter). The frozen commit's three remote CI jobs
all passed: https://github.com/shouldnotappearcalm/stock-rsi-lab/actions/runs/39614089971.
The earlier CI repair installed the declared HTML-parser test dependency in
both jobs; no test or notification was disabled.

The objective remains active and unachieved. Preserve this candidate's
inapplicability result. Any subsequent candidate must have its investment
definition, source admission and short/insufficient-month behavior fixed from
development evidence or independent methodology before 2026 application.
Changing this candidate's minimum after seeing the evaluation calendar would
not be the same frozen strategy.
