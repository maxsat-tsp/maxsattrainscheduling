# Audited stop at 174/186 cases

Captured on 2026-11-06 after the V13 worker failure at 14:28:54 UTC.
All 174 completed, receipted cases passed independent local schedule/cost
audit. MiniSAT finished 93/93; CaDiCaL finished 81/93. This is an incomplete
difficult-subset comparison, not full-dataset coverage.

The unreceipted CaDiCaL Orders-Transitive case
`stationA12/infsteps180` was killed by the external guard (exit 124), with no
final solver JSON/metadata. The native SAT adapter did not interrupt an
individual SAT query at the global deadline. It remains a failed attempt,
not an accepted ordinary timeout or an optimality proof. Its raw logs and
JSON are preserved in the archive and excluded from the 174 reusable cases.

On the same 25 completed continuous-objective pairs:

| Method | MiniSAT optimum | CaDiCaL optimum | MiniSAT PAR-2 (s) | CaDiCaL PAR-2 (s) |
|---|---:|---:|---:|---:|
| Orders-Transitive | 15/25 | 14/25 | 257.221 | 283.126 |
| CSOnet | 15/25 | 14/25 | 269.121 | 279.776 |
| MaxSAT-Journal | 16/25 | 12/25 | 257.919 | 317.518 |

Runtime retains mixed historical/sequential and new/parallel provenance.
These are development comparisons. Use `backend_parallel_same_binary.csv`
for the strictly matching new-binary execution cohort. No final backend or
SOTA conclusion is made before the remaining cases finish.

Across all 31 selected pairs, MiniSAT proves 1/5 rounded cases with each
method; continuous counts are 15/26, 15/26 and 16/26 respectively. Median
SAT time is almost the total time, so the next targeted idea reduces the
conflict cores rather than adding another refinement-selection mechanism.

Raw archive SHA-256:
`ad0f882fcd08f16dba9c749ca456fac440905effdc44f5bcdcec9ac493e7ad8b`.
It includes the failure evidence. Extract into a new directory, then audit
the completed receipts using `compare_sat_backends.py audit <directory>`.
The saved failure marker describes the campaign stop; it does not invalidate
individually verified earlier cases.

V14 fixes native interruption, preserves all 174 raw completed results and
runs only the 12 missing CaDiCaL cases. The stopped V13 source is unchanged.
