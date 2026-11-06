# Partial V16 capture: C1000 6/15, C100 3/15

Captured at 17:12:48 UTC on 2026-11-06, while both services remained active.
Both immutable snapshots were downloaded and independently audited locally.
All nine captured cases have valid statuses, schedules when present, costs,
parameters and provenance. The remaining cases are not results yet.

**C1000 proved `origB11/cont` optimal at 75,494 in 153.3911 seconds.** The
schedule is independently valid and `cost=lb=ub`. The prior Orders-Transitive
MiniSAT run timed out at 300 seconds with LB 75,481 and UB 75,494. CSOnet
and MaxSAT-Journal already solved this case, so this is a gain relative to
the candidate, not a new win over the SOTA ensemble.

The successful run removed 2,905 core literals across 2,373 extra checks,
with no inconclusive extra checks for this instance. Core reduction took
31.126 seconds within 153.275 seconds of native SAT time. The model had
49,890 variables and 163,456 clauses, compared with 66,414 variables and
230,383 clauses at the prior candidate timeout. These measurements motivate
finishing the trial; they do not establish full-dataset improvements.

C1000's other five captured cases and all three C100 cases are valid
timeouts. In particular, both profiles now terminate
`stationA11/infsteps180` normally rather than exiting with the external
guard's code 124.

Archive hashes and capture counts are in `capture.json`. Each archive has a
per-file checksum index. Audit extracted data using:

```bash
python3 quick_scripts/analyze/audit_targeted_core_minimization.py audit \
  <extracted-profile> --reference <original-v14-186-reference>
```

Keep the original V14 manifest/report bytes for the locked reference hashes.
`audit_passed=true` covers only this captured prefix; `complete=false` and
`submission_passed=false` remain in both independent reports. Three repeats
of the selected profile's gains and regression checks are still required.
