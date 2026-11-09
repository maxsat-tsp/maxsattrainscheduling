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

The service `maxsat-sat-bound-search-v41.service` completed a controlled
round of less than six hours in its separate worktree. It tested
the 13 V17 hard pairs and the V40 regression loss infsteps180/stationA8.
Each new gain triggered three confirmations and regression on the remaining
previously solved pairs, reusing cases already measured in this same round.
The bound pool includes V40: finding UB 118 again is not a new known bound.

The earlier preflight snapshot contains **preflight only**. The completed
campaign and its measured coverage are recorded in the next section. `independent_preflight_audit.json` records the
checks; `preflight_snapshot.tar.gz` preserves raw tests, smokes, deadline
probe, build/dependency provenance and the 14-case campaign manifest.

VM root:
`/home/tuyenkv/projects/sat-bound-search-v41/results/aglr/sat-bound-search-v41-20261109/`.
Read `hard-priority-evaluation.json` after the hard phase and
`followup-priority-evaluation.json` only after full confirmation/regression.

## Completed campaign and independent full audit

The controlled round completed successfully. `complete_snapshot.tar.gz`
preserves the full campaign, and `full_evaluation.json` independently
rechecks all schedules/costs, replays every bound update, and requires
exactly 216 distinct nonrepeat pairs with the same frozen source/binary.
Six confirmations are kept separate from coverage.

| Objective | V17 / 300 s | V40 / 300 s | V41 / 300 s |
|---|---:|---:|---:|
| finsteps123 | 72 | 72 | 72 |
| infsteps180 | 68 | 67 | 67 |
| cont | 63 | 64 | 65 |
| Total | 203 | 203 | 204 |

Relative to V17, V41 gains `cont/origA8` (23143, 55.139021 seconds) and
`cont/stationA2` (9193, 163.733396 seconds). Both reproduce in all three
confirmations: origA8 55.306112 / 55.224009 / 54.984624 seconds; stationA2
163.513513 / 163.515240 / 163.524238 seconds. It still loses
`infsteps180/stationA8`, timeout with its own [160,162], versus V17's
optimum 161 in 44.761233 seconds. Thus total coverage improves by one,
but the objective-wise nonregression condition is not met. No SOTA or
submission claim is made. Full-120 Gurobi already proves at least 206.

No remaining case improves a bound over all imported historical SAT/MILP
sources; two improve a bound over prior SAT runs. In particular V41's
infsteps180/trackA12 UB 125 does not improve V40's known UB 118. Candidate
bounds are never replaced by pooled reference bounds.

`full_reference_pool.json` and its SHA-256 receipt freeze the comparison
sources. `full_summary.csv` and `unresolved_bounds.csv` are derived from
the full audit. The earlier preflight-only snapshot/report above remains
unchanged; it is not relabeled as a completed experiment. The twelve
unresolved pairs in this complete archive form the next development set.
