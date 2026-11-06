# Targeted core reduction on unresolved MiniSAT cases

MiniSAT completed all 93 backend-comparison cases. On the common 25
continuous-objective pairs it proves more optima than CaDiCaL for all three
methods. Telemetry shows that SAT dominates total time. V15 therefore keeps
the MiniSAT Orders-Transitive method and changes only core reduction:
up to four extra SAT checks per core, each deletion accepted only after a
new UNSAT proof. All other method components stay unchanged.

The script reads the immutable, audited V13 reference and selects exactly
15 unresolved candidate pairs: 4 rounded and 11 continuous. It does not
rerun solved cases or baselines. This tests whether extra proofs can be
obtained, not whether previously solved cases remain solved. Any promising
result needs regression checks and confirmation before a full-dataset claim.

The trial started at 14:52:06 UTC on 2026-11-06 (21:52 Vietnam), service
`maxsat-core-v15-unresolved300.service`. Controller source `a417f3d`, binary
source `1908b22`, timeout 300 seconds, RAM limit 6,000,000 KB, CPUs
`0,1,4,5`. CaDiCaL's remaining backend-comparison cases run independently
on CPUs `2,3,6,7`. This trial is limited to a six-hour round.

68 Python tests passed on the VM; the shared binary has passed 49 Rust
library tests. A native MiniSAT smoke run with core checks enabled proved
cost 5526 on `origA1/cont` and performed 111 extra queries across its cores.
These checks validate behavior, not performance improvements.

Use `quick_scripts/analyze/targeted_core_minimization.py`; the full command
is in the runbook. Results live at
`/home/tuyenkv/projects/core-v15/maxsattrainscheduling/results/aglr/core-v15-unresolved300`.
`core_minimization_audit.json` lists `newly_solved` and the completed count.
Every returned schedule is independently checked, as are optimum costs
against already verified references where available. No SOTA or submission
claim follows from this subset alone.
