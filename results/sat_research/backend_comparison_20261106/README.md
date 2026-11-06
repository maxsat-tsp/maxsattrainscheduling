# MiniSAT and CaDiCaL in parallel

This development trial compares both SAT backends for Orders-Transitive,
CSOnet and MaxSAT-Journal, on the same 31 difficult instance/objective pairs
at 300 seconds. There are 186 SAT measurements. MILP results are retained
separately and are not repeated to compare SAT backends.

The trial started on 2026-11-06 at 11:07:06 UTC (18:07 Vietnam), service
`maxsat-backends300-v13-fabcc5a.service`. It imports 54 completed MiniSAT and
15 completed CaDiCaL measurements unchanged, leaving 117 new measurements.
Only cases listed as completed in independently audited source reports are
imported; interrupted cases are excluded. Sources are locked by manifest,
audit and individual JSON hashes. Source campaigns remain unchanged.

New measurements use the same release binary built from `4a43a9c`. The
controller/worker source is pinned to `fabcc5a`. MiniSAT uses CPUs `0,1,4,5`
(physical cores 0,1); CaDiCaL uses `2,3,6,7` (cores 2,3). Both have a
6,000,000 KB per-case address-space limit. There are two concurrent workers,
each processing a single case at a time. The VM has 8 logical CPUs, 4
physical cores and approximately 16 GB RAM. Up to three resumable rounds
are allowed, each at most six hours.

The original sequential measurements retain their original binaries and RAM
limits. Reusing those software versions for development follows the user's
earlier instruction; the report does not relabel them as fresh measurements.
The JSON and CSV compare only matching completed cases for each method and
objective. Coverage is primary; PAR-2 is secondary development evidence.
`backend_parallel_same_binary.csv` separates fresh measurements made with
the common binary in parallel mode. Final timing claims require sequential
confirmation of the decisive cases after choosing the method/backend.

VM result directory:
`/home/tuyenkv/projects/backends-v13/maxsattrainscheduling/results/aglr/backends300-v13-fabcc5a`.
Read `backend_comparison.json`, `backend_comparison.csv`, `minisat.log`, and
`cadical.log`. `complete=true` means the difficult subset is complete, not
that the full dataset or submission gate has passed. Either worker failing
stops the round, preserves raw data and records `failure.json`.

65 Python tests and a six-case native parallel smoke test passed on the VM
before launch. Both backends proved optimum 5526 for all three MaxSAT methods
on `origA1/cont`. A subsequent read-only audit fix passes 66 tests and can
audit the live trial without competing with its report writer. It does not
change the locked running workers or solver binary.

See `launch.json` for exact hashes. Use `run_sat_backend_comparison.sh` for
resume and the runbook for the environment and live audit command.
