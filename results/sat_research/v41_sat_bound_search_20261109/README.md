# V41: test UB minus one when the relative gap is at most 5%

Source is frozen at `76bff0c`; binary SHA-256 is
`327fdcb59ad839e2c86390b2245948240170ad5f6c60a359722e617c64df9ec6`.
Only threshold selection changes relative to V40. MiniSAT, cost encoding,
resource orders, transitivity and the shared 300-second instance deadline
are retained. No optimum/reference schedule enters the solver.

The `close-upper` policy selects UB-1 if `100*(UB-LB) <= 5*max(1,UB)`;
otherwise it uses V40 bisection. SAT may improve the incumbent; UNSAT at
UB-1 proves its optimality. UNKNOWN changes neither bound. The default
`bisect` policy retains the old threshold rule.

Native preflight passed 7 search/exhaustive tests, 5 binary objective tests,
166 Python tests, three real-case smoke optima (11,34,5526), and a native
0.05-second timeout probe. After download, all 55 Rust source hashes were
checked against the frozen commit. Smoke/probe receipts, schedules, trace
ledgers and query budgets were checked independently again.

The service `maxsat-sat-bound-search-v41.service` is enabled and runs a
controlled round of at most six hours in its separate worktree. It tests
the 13 V17 hard pairs and the V40 regression loss infsteps180/stationA8.
Any new gain triggers three confirmations and regression on the remaining
previously solved pairs, reusing cases already measured in this same round.
The bound pool includes V40: finding UB 118 again is not a new known bound.

This snapshot contains **preflight only**, no hard-case outcome and no
coverage improvement claim. `independent_preflight_audit.json` records the
checks; `preflight_snapshot.tar.gz` preserves raw tests, smokes, deadline
probe, build/dependency provenance and the 14-case campaign manifest.

VM root:
`/home/tuyenkv/projects/sat-bound-search-v41/results/aglr/sat-bound-search-v41-20261109/`.
Read `hard-priority-evaluation.json` after the hard phase and
`followup-priority-evaluation.json` only after full confirmation/regression.
