# V18: optional positive temporal-cycle cuts

Source `5e70580`; isolated VM service `maxsat-order-cycles-v18.service`.
Started 01:10:16 UTC, 2026-11-07. The controller first runs all Rust/Python
tests, builds a release and validates a known optimum and native timeout.
Only after these checks does it measure the 13 pairs unresolved by V17.
The full V17 reference is audited and locked; its 203 solved cases and
all existing baselines are not rerun during this screening round.

The single new algorithmic component forbids positive temporal cycles
among existing resource-order bits and fixed route edges. Nonfinal
occupations use their actual next-visit exit. Zero-weight cycles remain
allowed. Only full SAT models are separated, one clause at a time.
The flag is false by default; CSOnet remains unchanged.

There is no performance claim in this launch receipt. Results, if any,
need independent auditing, three confirmations of gains and regression
before upgrading the full-dataset coverage. No submission pass is implied.
The complete round, including tests and build, is limited to six hours.

The initial test/build launch did not run performance cases. Its new fixture
exposed an existing early-return limitation for a feasible initial schedule
with positive cost. A second test launch stopped because its assertion
required a full SAT call even when verified bounds had already met. That
fixture also conflicted with the heuristic's resource-0 terminal convention.
Both failed test logs are preserved; no measured result was discarded.

The successor source is `ca96ae5`, service `maxsat-order-cycles-v18-v3.service`,
started 01:18:58 UTC. See `successor_launch.json`. The forced-model MiniSAT
truth table still checks actual cycle clauses; the end-to-end test checks
all three optima with both SAT backends and permits an early verified optimum.
`initial_cost_dataset_check.json` checks all 72 benchmark initial schedules:
each has conflicts, so the specific already-feasible early-return limitation
does not trigger on their initial state. It does not replace per-result audits.

The successor passed all 63 Rust and 94 Python tests, both known-cost
smokes and the native timeout probe. The 13-case run started at 01:19:45 UTC.
`validation_snapshot.tar.gz` retains the logs and raw smokes; see the build
manifest and `validation_sha256.json`. Binary SHA-256:
`5b3f0829650deee56f5d6b4f89111d3b7901f16374fa8734ac94cd85a379638f`.

`v17_unresolved_telemetry.csv` records diagnostics for planning. The last
two columns are parsed from the retained stdout (last logged LB and best
heuristic UB), because native-deadline JSON did not retain those bounds.
They are diagnostic log values, not new optimality certificates or changes
to any raw JSON.
