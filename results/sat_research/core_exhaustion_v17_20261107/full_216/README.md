# Completed V17 full216

All schedules and bounds were independently checked after download.
The raw JSON, logs and receipts remain unchanged in `raw_snapshot.tar.gz`.
`independent_audit.json` records reconstructed counts and summaries.

Solver source: `43cae7674338e0468db1c7be04c446cddb983eef`. Runner: `438129f7b891a90f74b7ec1ef2907916a106ad88`.
Timeout: 300 s; sequential CPU affinity 0,1,4,5; RAM 6,000,000 KB.
This configuration uses legacy refinement, resource orders and RC2 core
processing. It is not a result for the adaptive AGLR selector.

For full coverage, 31 previously measured cases were reused byte for byte
and only the 185 other cases were measured. The candidate reaches
(72,68,63), total 203/216. Same-cutoff matched comparisons against the
three MaxSAT methods cover the 31 difficult pairs only. This is not a
submission pass or proof of superiority to every MILP baseline.
