# Six V16 confirmations independently verified

C100 reproduced both gained optima in all three sequential repeats.
All six schedules were downloaded and independently checked against the
instances, costs, bounds, runtime limits, configuration and source/binary
provenance. The source-profile hashes are also checked.

| Instance / objective | Cost = LB = UB | Repeats | Median seconds | Range seconds |
|---|---:|---:|---:|---|
| origB11 / cont | 75,494 | 3/3 | 182.2497 | 137.7165–205.7424 |
| stationB12 / cont | 16,909 | 3/3 | 5.6700 | 1.7543–15.3880 |

The full distribution is retained rather than substituting the fastest
screening run. These repeats confirm the two gains; regression on other
cases is a separate check. The subsequent regression lost stationA9, so
these six successful repeats do not establish a full-dataset win.

Archive SHA-256:
`7b043c6f4f2cedfc9d0c49af05b7f4680766f346406261b7702f8aa75a189ecc`.
`snapshot_confirmation.py` records every file hash. To reproduce the
independent audit from the repository root after extracting the archives:

```bash
python3 results/sat_research/limited_core_v16_20261106/confirmation_complete/audit_confirmation.py \
  <confirmation-directory> --reference <v14-reference> \
  --profiles <c1000-directory> <c100-directory>
```

`independent_audit.json` contains the reconstructed six outcomes and summary.
Submission remains false; these technical repeats are not independent
benchmark instances.
