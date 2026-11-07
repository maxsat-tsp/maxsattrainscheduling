# V27: guarded single-order objective lower bounds before search

Source c1b046f; initial seeding is optional and off by default. Build and
native checks are queued only after V26 finishes. The decision script
independently audits all 13 V26 results and the 216-case V17 reference.
If V26 has a gain, skip V27 and retain its gain confirmations/regression.
Missing, incomplete or invalid V26 evidence stops the queued round.

V27 derives only hard route earliest bounds, uses the actual departure
node or the positive-duration final occupation, and propagates a single
conditional order down the receiving train's route. It seeds only visits
with increased objective cost; canonical points are shared and registered
before SAT. No reference cost/schedule enters the solver. Relative to
V26, only order_master_seed_costs=true changes.

Local checks: 37 kernel/backend tests, 113 Python tests, Rust library/bin/
test typechecks, Bash syntax. Native Rust checks remain mandatory. The
static CSV is a size estimate using the independent TXT parser, not a
solver timing or a native correctness result. Actual seed counts must be
read from native telemetry. See the student guide for the proof/example.

Screen only four infsteps180 pairs at 300 seconds and 6,000,000 KB, serial
CPUs 0,1,4,5; six-hour cap includes waiting. If gains occur, confirm three
times and regress the 68 solved rounded-objective pairs. Scoped followup
cannot claim full coverage or submission success.
