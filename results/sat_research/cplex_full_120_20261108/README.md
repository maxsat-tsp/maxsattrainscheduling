# Corrected Big-M CPLEX full baseline (120 seconds)

All 216 objective-instance cases were run with the corrected `export_lp` binary and CPLEX 22.2. Raw case directories from the first pass are preserved in `raw_snapshot.tar.gz`; `cplex_summary.csv` and `independent_audit.json` were rebuilt by checking every valid schedule and requiring `cost=lb=ub` for a proven optimum.

The first pass proved 204 optima. The only invalid incumbent, `infsteps180/trackA8`, was rerun with CPLEX integrality tolerance `1e-9`; the tight rerun produced a valid schedule with `cost=lb=ub=146`. The corrected baseline therefore proves `finsteps123` 72/72, `infsteps180` 67/72, and `cont` 66/72, total 205/216. Five `infsteps180` and six `cont` cases remain valid but inconclusive. The first invalid raw run and the tight rerun are both preserved.

The `cplex_csv/` files are ready for the AGLR campaign auditor. Parallel timings are diagnostic; final runtime comparison requires sequential timings.

## 09 November: cross-method optimum correction

The archived finsteps123/trackA8 optimum 35 is contradicted by checked SAT
schedules of cost 34. A strict rerun on exactly the same LP confirms optimum
34. Use the derived `bound_recheck_20261109/cplex_csv/` for new comparisons;
the original CSVs are preserved as historical data. The full coverage stays
205/216. Native evidence, the rejected command attempt and a reproducible
CSV correction auditor are under `bound_recheck_20261109/`.
