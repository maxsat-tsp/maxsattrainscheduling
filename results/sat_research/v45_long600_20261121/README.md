# V45 and matched controls at 600 seconds

V45 at `c90cb63` proved **206/216** optima, with coverage
`(72, 68, 66)` for `finsteps123`, `infsteps180` and `cont`.
It retained all 205 cases solved by V42 at 300 seconds. On
`cont/stationA1` it proved optimum 12884 at 322.42 seconds.
Three independent reruns reproduced the same cost and matching
bounds in 324.49, 322.67 and 322.81 seconds. Both versions have
205 proofs by 300 seconds.

On the 11 matched hard cases at 600 seconds, V45 proved 1,
Gurobi and CPLEX each proved 3, and CSOnet and MaxSAT-Journal
proved 0. Each MILP reused three audited proofs from an earlier
cutoff. Three SAT records are external timeouts: two for CSOnet
and one for MaxSAT-Journal. Their wrapper receipts establish
censoring, with no credit for a proof or a bound.

On `infsteps180/stationA12`, a verified V45 schedule reduced
the best known UB from 143 to 142. Its own LB is 104 and the
strongest imported LB is 115. None of the other unresolved
pairs improved the best bounds in the matched comparison.

At 600 seconds, CPLEX has **208/216**. The inventory combines
208 audited proofs by 300 seconds with the eight remaining
observations at 600 seconds. The Gurobi inventory has 207
verified proofs and one outstanding observation at 600 seconds,
`infsteps180/stationA8`. Runtime comparisons across these
reused MILP runs are unavailable.

`complete_snapshot.tar.gz` contains both completed SAT phases,
all matched controls and their original receipts. Its top-level
`COMPLETED` copies the SAT marker `FOLLOWUP_COMPLETED` so the
archive can select V46's cases. The native `FAILED` marker for
the original CSOnet interruption and the separate recovery
results under `control-recovery/` are preserved. The recovered
controls ran with runner `a964d69`. `complete_replay.json`
records the independent replay and the MILP coverage inventory.

The initial data and checks remain in `native_initial_snapshot.tar.gz`,
`hard600_replay.json`, and `cplex300_audit.json`. The first confirmation
and its independent check are in `confirmation_1_snapshot.tar.gz` and
`confirmation_1_audit.json`. Hashes for these files and the complete
snapshot are in `archive_hashes.json`.
