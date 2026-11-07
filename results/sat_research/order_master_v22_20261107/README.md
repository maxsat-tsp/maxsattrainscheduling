# V22: validation stopped before hard-case screening

Native tests passed (76 Rust, 106 Python), but the known-cost smoke for
origA1/infsteps180 timed out at 30 seconds. The controller stopped before
any hard case. origA1/finsteps123 proved cost 11 in 18.7200 seconds. Both
raw records are independently audited in `stopped_validation/`. This is
not a completed 13-case performance trial. V23 will canonicalize thresholds
within equal-cost plateaus; no V22 result is discarded.

## Original implementation and launch record

# V22: complete resource-order master inside the CSOnet RC2 loop

Source `38f9aea`. V20 and V21 both completed 13 unresolved pairs without a
gain. V22 uses the same weighted RC2 loop, CostTree, core minimization and
core exhaustion as V17. It changes the representation: create all resource
orders, analyse the temporal graph for feasibility and earliest schedules,
and add threshold variables only at visits that contribute objective cost.
No time-indexed overlap rows or initial triangle clauses are created.
The historical transitivity flag remains recorded but the actual triangle
count is zero in this mode; it is not the same DDD encoding as V17.

The optional `order_master` flag is false by default; alias
`maxsat_order_graph` enables master mode and resource orders. The baseline
path stays unchanged. The old asynchronous heuristic is disabled only in
master mode: each acyclic orientation already produces a candidate schedule.
Every improving or closing schedule is independently checked in the solver.
No conference answer is available to the solver.

76 Rust tests pass natively. They include brute-force optima for final
positive-length occupations, initial positive costs, sparse cost encoding,
objective bounds and both MiniSAT/CaDiCaL, plus crossing routes and zero
components. The runner and gain-followup tests pass 106 Python tests locally;
the controller reruns all Python tests on the VM. Its initial pretest launch
failed before any code ran because the upload had not completed; the receipt
is retained and the corrected pretest passed without algorithm changes.

Before screening, the controller validates origA1 on all three objectives,
its dispatch alias and native timeout handling. Only 13 V17 unresolved pairs
are then screened, serially, at 300 seconds and 6,000,000 KB on CPUs 0,1,4,5.
The entire service has a six-hour cap. A completed clean gain triggers three
repeats with the same binary/configuration; only when all reproduce does it
regress the 203 solved V17 pairs. Losses and partial progress are retained.
All reports keep submission_passed=false; full table construction and an
independent followup audit remain separate. There is no performance claim
in this launch receipt.
