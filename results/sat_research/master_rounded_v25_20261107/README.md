# V25: four unresolved rounded-objective cases with the frozen V24 method

Runner source 7b752c4; solver source d8e2509; frozen binary SHA-256
6b9742deb3b1fe7d32426c3d3120064c976819468b4e08e896cfdbb8096918b8.
The V24 origA1/infsteps180 optimum is independently verified and reused.
V24 continuous-objective smoke remains a valid 30-second timeout; its raw
record is preserved separately. The V25 filter selects only trackA11,
trackA12, stationA11 and stationA12 under infsteps180, not all 13 pairs.

110 Python tests pass. Initial setup attempts failed before any hard case:
first on missing sibling dependency paths, then when attempting to rerun
an already recorded native deadline probe. Dependency links were repaired;
the validator now assesses the existing probe instead of rewriting it.
The actual hard-case screen service is maxsat-master-rounded-v25-screen,
started 2026-11-07 07:01:45 UTC (14:01:45 Vietnam). Initial failure and
probe records are retained separately on the VM and will be archived.

Run serial on CPUs 0,1,4,5, 300 seconds and 6,000,000 KB. On gains, confirm
three times and regress only the 68 solved rounded-objective pairs. A
scoped regression explicitly cannot claim full-reference coverage or
submission success; excluded objectives require separate locked evaluation.


Completed: four valid 300-second timeouts, no new optimum. See complete_4/
for the immutable raw snapshot, independent local audit, source manifests,
setup/followup archive and explicitly diagnostic bounds/telemetry CSV.
