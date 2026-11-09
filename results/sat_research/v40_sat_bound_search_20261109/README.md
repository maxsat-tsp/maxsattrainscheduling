# V40: autonomous SAT cost-threshold search, complete

Frozen solver source: `9ab1725`. MiniSAT, V17 resource orders/transitivity
and DDD refinement are retained; binary search replaces RC2 optimization.
The solver receives no optimum or reference schedule. Each instance has
one shared 300-second deadline across every threshold query.

## Full result and confirmations

All 13 hard cases, three gain confirmations and 203 regression cases have
completed. Every initial/incumbent/final schedule and cost was independently
checked again after download. Each LB/UB update and the common deadline were
replayed from the query ledger. Exact full membership and method identity
were checked; repetitions are not independent coverage observations.

| Objective | V17 at 300 s | V40 at 300 s | Change |
|---|---:|---:|---:|
| finsteps123 | 72 | 72 | 0 |
| infsteps180 | 68 | 67 | -1 |
| cont | 63 | 64 | +1 |
| Total | 203 | 203 | 0 |

The new proof is `cont/origA8`, cost=LB=UB=23143, 176.520220 seconds.
Three confirmations succeed at 177.179616, 175.713405 and 176.948636 seconds.
The lost pair is `infsteps180/stationA8`, timeout with its own bounds
[161,163]. This candidate does not improve total coverage or meet the
objective-wise nonregression gate. No SOTA/submission claim is made.

## Priority: optimal coverage, improved known bounds, then runtime

On `infsteps180/trackA12`, V40 returns an independently checked schedule of
cost 118, improving the best UB 125 in the imported historical SAT/MILP
sources. Its own LB is only 92, versus the previous best LB 106. Thus the
intervals are [92,118] and [106,125]: a new upper bound, with a weaker lower
bound. [106,118] combines evidence from different methods and is not V40's
own interval. There is one new-best-bound case among the unresolved pairs
and four cases improving at least one bound relative to imported SAT runs.

References include 120-, 300- and 600-second cutoffs. This identifies known
bounds, not equal-budget performance dominance. Reference timeout LBs/log
progress are explicitly solver-reported; available witnesses are checked.
`full_reference_pool.json` freezes sources and hashes. Its `.sha256` receipt
protects against changing that pool in later comparisons. The old V15
archive lacks an internal snapshot hash receipt and is explicitly excluded.

Cross-reference auditing flags CPLEX's claimed optimum 35 for
`finsteps123/trackA8`, contradicted by valid SAT schedules of cost 34. The
reported LB 35 is retained as `excluded_lower_bound` and quarantined from
the known-bound pool; its valid UB 35 is retained. This does not silently
repair the historical CPLEX coverage table. The conflict must be resolved
before using that table for submission.

## Files

- `complete_snapshot.tar.gz`: complete, unmodified VM campaign including
  hard cases, confirmations, regression, receipts, traces and native
  preflight evidence. The executable and lock file are excluded.
- `full_evaluation.json`: current independent full evaluation, including
  per-case bounds, source pool, gains/losses, confirmations and runtime.
- `full_summary.csv`, `unresolved_bounds.csv`: readable derived tables.
- `gurobi_infsteps180_source.json`: original full-120 source used in the
  bound comparison. The cont source remains in the V39 artifact directory.
- `raw_snapshot.tar.gz`, `independent_audit.json`, `validation_audit.json`:
  the preserved first snapshot with two completed cases; these historical
  files are not overwritten or relabeled as the complete experiment.
- `archive_hashes.json`: SHA-256 for all accompanying artifacts.

The original native preflight passed 5 search/exhaustive tests, 5 binary
cost tests, 144 Python tests, three real-case smokes and a deadline probe.
The new coverage/bounds evaluator additionally passed 164 Python tests on
both the local machine and VM, without rebuilding/replacing the V40 binary.

The service `maxsat-sat-bound-search-v40.service` completed successfully.
Raw root: `/home/tuyenkv/projects/sat-bound-search-v40/results/aglr/sat-bound-search-v40-20261109/`.
The separate read-only `maxsat-bound-priority-report.service` completed its
reports under that root's `evaluation/`, using frozen checkout `15dd0e6`.
