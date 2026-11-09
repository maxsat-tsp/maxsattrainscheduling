# V37: bounded whole-core trimming, completed

All 13 V17-unresolved pairs timed out validly at 300 seconds. Independent
audit after download found no errors and no new optimum. V17 remains the
strongest fully measured SAT configuration at (72,68,63) = 203/216.

The raw snapshot includes the original JSON, logs, launch manifests, native
test logs, smoke schedules, binary hash and source hashes. The executable
itself is excluded from the archive. The recorded Rust source hashes were
checked against commit `5c6fdbc`; all six smoke schedules were independently
verified after download. Native validation passed six core tests and one
exhaustive scheduling test; 128 Python tests passed on the VM.

`telemetry.csv` records trimming activity on all 13 pairs. Trimming removed
redundant assumptions but never increased the minimum core weight. Its
accumulated time stayed below one second per case. This is diagnostic
evidence, with no coverage improvement or SOTA claim.

MiniSAT, resource orders, transitivity and V17 core settings were retained;
only whole-core trimming was enabled, with at most three queries per core.
The V30 deterministic tie ordering was also retained in this newer binary.
Raw results are immutable in `raw_snapshot.tar.gz`; the independent report
is `independent_audit.json`, and smoke/source verification is recorded in
`validation_audit.json`.

V38 keeps trimming disabled and tests proved intrinsic-AM1 adaptation.
