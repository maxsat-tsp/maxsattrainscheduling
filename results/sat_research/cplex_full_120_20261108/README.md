# Corrected Big-M CPLEX full baseline (120 seconds)

All 216 objective-instance cases were run with the corrected `export_lp` binary and CPLEX 22.2. Raw case directories are preserved in `raw_snapshot.tar.gz`; `cplex_summary.csv` and `independent_audit.json` were rebuilt by checking every valid schedule and requiring `cost=lb=ub` for a proven optimum.

The campaign proves 204 optima: `finsteps123` 72/72, `infsteps180` 66/72, and `cont` 66/72. Eleven additional cases returned valid but inconclusive incumbents. One case, `infsteps180/trackA8`, produced an invalid incumbent with a resource overlap and is marked `invalid_solution`, not counted as a valid schedule or optimum.

The `cplex_csv/` files are ready for the AGLR campaign auditor. Parallel timings are diagnostic; final runtime comparison requires sequential timings.
