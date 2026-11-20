# V45 at 600 seconds and CPLEX at 300 seconds

The 11 hard cases completed with the frozen V45 reuse method at
`c90cb63`. Independent replay verified the source hashes, schedules,
costs, query records and receipts. The hard-set outcome is **1/11
proved optimal**. Full-dataset confirmation and regression are underway.

On `cont/stationA1`, SAT found a schedule of cost 12884 at about
246 seconds. The decision at 12883 proved UNSAT in about 76 seconds,
closing the interval at 12884 in 322.42 seconds. The known Big-M
optimum was used for audit only. An independently checked schedule
also lowers UB from 143 to 142 on `infsteps180/stationA12`.
V45's own LB is 104 and the strongest imported LB is 115.

CPLEX completed the 11 outstanding 300-second observations. It
proves **208/216** across the dataset (72, 68, 68), including three
additional cases in the corrected extension. Gurobi has 207/216.
At 600 seconds the two MILP controls each prove 3/11 on the matched
hard set, with three checked earlier proofs reused by each.

CSOnet supplied eight native results. On its ninth case,
`infsteps180/trackA12`, the wrapper recorded exit 124 at 620.016
wall seconds. The launch and both result copies agree. This
observation is recorded as external censoring, without a witness
or any bound. The original failed campaign is preserved.

`native_initial_snapshot.tar.gz` contains the original VM data
and receipts. `cplex300_audit.json` is the independent CPLEX replay.
`hard600_replay.json` contains the V45 replay and control evidence
through the interruption. The original V45 binary is running the
three confirmations and then the 205 regressions. Recovery source
`a964d69` waits for it before completing the two remaining CSOnet
cases and the MaxSAT-Journal control.

The first confirmation independently replayed the same optimum
12884 in 324.49 seconds. Its manifest, result and receipt are in
`confirmation_1_snapshot.tar.gz`, with the replay in
`confirmation_1_audit.json`.
