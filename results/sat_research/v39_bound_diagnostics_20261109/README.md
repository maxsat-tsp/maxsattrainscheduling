# V39: diagnose why MaxSAT fails on instances solved by Big-M

This directory initially records oracle selection, before the VM diagnostics.
It does **not** report a new MaxSAT optimum or an improvement in coverage.

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

The VM campaign uses pinned source `ce89553`, MiniSAT and the V17 settings.
For every selected pair it will run `at-opt`, `below-opt`, `oracle-ub` and
`control`, serially, at 300 seconds per query and 6,000,000 KB. It waits for
V38, requires native arithmetic/exhaustive tests and real-instance smoke
checks, then independently audits the results. The service has a six-hour
limit. The source was type-checked locally and all 136 Python tests passed;
native VM validation and diagnostic outcomes are still pending in this
initial record.

The fixed-threshold queries disable RC2 cost assumptions but retain DDD
refinement and the tested binary cost bound. The `oracle-ub` mode supplies a
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
