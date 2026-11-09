# V39: diagnose why MaxSAT fails on instances solved by Big-M

This directory preserves oracle selection and all sixteen VM diagnostics.
It does **not** report a new autonomous MaxSAT optimum or an improvement in coverage.
`oracle_selection_audit.json` records the initial oracle selection only.

The exact existing Gurobi `cont.json` is preserved as
`gurobi_cont_source.json`. Its four valid optimal schedules on unresolved V17
pairs have been independently checked with the Python instance parser and
schedule verifier. All four satisfy `cost=lb=ub`:

| Instance | Big-M optimum | Last LB printed by V17 at 300 s | Printed LB updates of size 1 / all updates |
|---|---:|---:|---:|
| origA8 | 23143 | 22736 | 487 / 598 |
| stationA1 | 12884 | 12745 | 366 / 519 |
| stationA2 | 9193 | 8398 | 799 / 901 |
| trackA8 | 24441 | 21064 | 952 / 1249 |

These are printed progress values, not final certified bounds recovered from
the timeout JSON. The heuristic's printed candidate costs omit the initial
greedy incumbent and therefore do not establish the final maintained UB.

The VM campaign uses pinned source `21998ae`, MiniSAT and the V17 settings.
For every selected pair it will run `at-opt`, `below-opt`, `oracle-ub` and
`control`, serially, at 300 seconds per query and 6,000,000 KB. It waits for
V38, requires native arithmetic/exhaustive tests and real-instance smoke
checks, then independently audits the results. The service has a six-hour
limit. Native VM validation passed three exhaustive/diagnostic tests, five
arithmetic tests, 136 Python tests, three ordinary-CLI smokes and twelve
diagnostic smokes. All fifteen downloaded smoke schedules/outcomes and
the recorded Rust source hashes were independently checked.

## Complete independently audited diagnostics

All sixteen runs completed without audit errors. All four RC2 controls and
all four optimal-incumbent-only RC2 runs timed out at 300 seconds.

| cont instance | Optimum | SAT at optimum (s) | UNSAT below optimum (s) |
|---|---:|---:|---:|
| origA8 | 23143 | 15.798933 | 16.911099 |
| stationA1 | 12884 | 210.131921 | 163.585725 |
| stationA2 | 9193 | 84.024499 | 75.594220 |
| trackA8 | 24441 | timeout 300 | timeout 300 |

The `stationA2` result also motivates threshold search; `trackA8` shows that
even a known optimal threshold does not make every SAT decision easy.
The costs supplied by the oracle remain diagnostic inputs, never coverage.

## Detailed origA8 comparison

For `cont/origA8`, with independently verified optimum 23143:

| Query | Result | Seconds | Native SAT calls |
|---|---|---:|---:|
| Find a schedule with cost <= 23143 | SAT, verified cost 23143 | 15.798933 | 265 |
| Exclude schedules with cost <= 23142 | UNSAT | 16.911099 | 274 |
| RC2 given the verified optimal incumbent only | timeout | 300.011518 | 8455 |
| RC2 control, same new binary without oracle input to the solver | timeout | 300.009503 | 8461 |

RC2's last recorded lower bound in the third query is 22679; its supplied
upper bound is 23143. Thus supplying an optimal incumbent alone does not
remove the bottleneck on this instance. The two direct threshold queries
are far easier than the current core-guided optimization process here.
This motivates testing SAT search over objective thresholds without oracle
information. It is not yet an autonomous optimization or a full-campaign claim.
The control's last recorded LB/UB are 22680/23648, with the same final counts
of 60025 variables and 232497 clauses as the oracle-UB timeout. These are
last recorded progress bounds, not a fabricated closed-gap optimum.

`cont/stationA1` has a different pattern: with optimum 12884 given as the
threshold, finding the schedule takes 210.131921 seconds (222 native calls),
and excluding cost <= 12883 takes 163.585725 seconds (256 calls). Native SAT
accounts for almost all that time. The endpoint queries themselves are
expensive here; changing objective search alone is not established as a
general solution. Interpret each instance separately.

`raw_snapshot.tar.gz` contains only completed cases, native test logs, smokes,
build/source hashes and the exact MIP source files. Running cases are excluded.
`independent_audit.json` checks all 16/16 runs; `diagnostics.csv` gives the
complete per-query table. The V39 service finished and the next round uses
autonomous threshold selection without a MIP optimum as a solver input.

The fixed-threshold queries disable RC2 cost assumptions but retain DDD
refinement and the tested binary cost bound, whose initial budget is fixed at
the queried threshold while unused budget is allowed. The `oracle-ub` mode supplies a
verified schedule without setting RC2's LB or inserting oracle time points;
it disables the now-unnecessary graph heuristic. `control` receives no oracle
information inside the solver. Every diagnostic is ineligible for the
submission coverage table.

Interpret results per instance. Fast feasible/UNSAT threshold queries with a
slow control would motivate changing the bound search. A fast feasible query
but a slow `opt-1` proof would point toward difficulty proving optimality.
If the SAT queries also time out, inspect encoding growth and SAT time before
attributing the failure to the search over objective levels.

VM service: `maxsat-bound-diagnostics-v39.service`.
Campaign: `/home/tuyenkv/projects/bound-diagnostics-v39/results/aglr/bound-diagnostics-v39-20261109/`.
