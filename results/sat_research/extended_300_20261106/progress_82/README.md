# Partial snapshot: 82/155 runs, 300-second common cutoff

This snapshot contains 82 completed runs, including 16 cont pairs completed
by all five methods. The remaining campaign continues unchanged on the VM.
Every completed JSON schedule was independently audited locally; the report
was rebuilt from raw cases. Small machine-rounding differences (about 1e-14)
are accepted only in derived runtime statistics, never in costs or coverage.

| Method | Optimal on the same 16 cont pairs | PAR-2 (s) |
|---|---:|---:|
| Orders-Transitive | 10/16 | 249.769 |
| CSOnet | 10/16 | 267.611 |
| MaxSAT-Journal | 10/16 | 270.233 |
| Big-M Gurobi | 13/16 | 117.357 |
| Big-M CPLEX | 13/16 | 117.636 |

Orders-Transitive completes stationA9/cont in 216.23 s and trackB12/cont in
132.12 s. CSOnet and MaxSAT-Journal complete stationA9 and origB11 after
120 s; the candidate times out on origB11. Increasing the common cutoff
therefore helps both the candidate and its baselines. It has not established
a coverage advantage for the candidate.

The original 120-second conference tables are historical context only.
These 16 pairs are a partial subset; no full-dataset or SOTA claim follows.
The report's seventh after-120 result, CPLEX on stationA8, belongs to a pair
whose remaining methods had not all finished when this snapshot was taken.

Raw archive SHA-256:
`a2fbe12138b72600ae3f1ff30a194f97e5ed636f10871c543eeb5caf64660f98`.

To reproduce the independent audit, extract the archive into a new directory
and run `extended_timeout_experiments.py audit-saved <directory>`.
