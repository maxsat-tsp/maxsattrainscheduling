# C1000 complete: two gains on the 15 previously unresolved pairs

All 15 cases were downloaded and independently audited locally. There are
no invalid schedules, cost/bound disagreements, external timeouts or missing
cases in this profile. Four rounded-objective cases and nine continuous
cases remain valid timeouts.

| New candidate optimum | Cost = LB = UB | C1000 seconds | Prior candidate | MaxSAT-Journal seconds |
|---|---:|---:|---|---:|
| origB11 / cont | 75,494 | 153.3911 | timeout at 300 s | 270.3129 |
| stationB12 / cont | 16,909 | 34.5859 | timeout at 300 s | 290.3816 |

These are gains relative to the prior Orders-Transitive configuration.
Both instances were already solved by MaxSAT-Journal. The historical
reference and parallel parameter-screening timings retain their different
measurement conditions; they are not a three-repeat runtime confirmation.

For stationB12, core reduction removed 4,021 literals and took 2.4981 seconds.
The completed model has 46,901 variables and 120,795 clauses; the old
candidate timeout had 122,756 variables and 353,678 clauses. Every successful
schedule has been checked against the original instance and objective.

At this capture C100 had not finished. Its later complete profile is in
`../c100_complete/`; both profiles gain two cases, and C100 was selected by
PAR-2 for confirmation. The selected gains need three successful repeats and
regression on the 16 previously solved difficult pairs. These checks are queued. This 15-pair profile does
not establish a complete 72-instance coverage result or a submission pass.

Archive SHA-256:
`9784f52fc31205650e533f1e5342f9672b26719ae4525dde3348e8a709535667`.
The archive has a checksum index for every file. Audit extracted data with:

```bash
python3 quick_scripts/analyze/audit_targeted_core_minimization.py audit \
  <extracted-c1000> --reference <original-completed-v14-reference>
```
