# V26: batch all violated objective paths from one order-master model

Solver and runner source: 984e221. Defaults and the published legacy path
remain unchanged. This optional component retains V24 canonical thresholds
and full assumptions, adds each independently proved cost-path clause, then
registers every new point in CostTree before the next SAT call.

Local checks pass: 36 kernel/backend tests, 111 Python tests, Rust typecheck
for the library, executable and test targets, Bash syntax and diff checks.
The controller waits for V25 to stop before native Rust tests, release build
and timing. Native solver tests must pass; no native pass is inferred while
queued. Every proved real-case smoke must match its known optimum. Valid
30-second real-case timeouts are retained as performance outcomes; at least
one smoke must prove its optimum and multi-cut separation must be exercised.
This explicitly differs from the early performance stop used by V22--V24.

Screen all 13 V17 unresolved pairs, serial on CPUs 0,1,4,5, 300 seconds and
6,000,000 KB each. The six-hour service cap includes the queue wait. Audit,
three repeats of gains and 203 solved-pair regression remain mandatory
before constructing a new full table. submission_passed remains false.


Validator revision: assess existing smoke/probe JSON without rerunning it.
An absent partial-SAT counter is accepted only for an independently valid
native timeout with assumptions=full; it is recorded as missing telemetry,
not filled with zero. Proved results still require the counter and exact
known optimum. The controller retains the initial absolute round deadline
across validator-only restarts, so followup cannot reset the six-hour budget.


Completed: all 13 pairs timed out validly at 300 seconds, independently
audited locally. See complete_13/ for the immutable raw archive, regenerated
summary and separate diagnostic bounds/telemetry CSV. No coverage gain.
