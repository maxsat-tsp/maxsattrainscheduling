# V17 complete on 14 unresolved or regressed pairs

All 14 cases passed independent local audit with both V16 profiles and the
complete regression as hashed selection references. `stationA9/cont` was
recovered at cost=LB=UB=7,655 in 45.4647 seconds. The other nine continuous
and all four rounded-objective cases remain valid timeouts.

This recovery returns a known optimum rather than solving an instance
outside the previous methods' coverage. The configuration still needs
validation on the other 17 pairs before assigning it a 31-pair coverage.
That completion reuses all 14 raw cases unchanged.

Core exhaustion raised cardinality floors on some continuous cases but
raised none on the four rounded cases or the recovered stationA9 run.
Consequently the stationA9 timing cannot be attributed to floor increases
from this evidence. Extra SAT learning and assumption-order variation are
possible factors. Raw counters are retained for diagnosis.

Archive SHA-256:
`ce33a161e5c59d2a008dec1b7fd6b0a2e4e39a5763a76c227499c095ee9d8796`.

```bash
python3 quick_scripts/analyze/audit_targeted_core_minimization.py audit \
  <extracted-v17> --reference <v14-reference> \
  --previous-trials <c1000-directory> <c100-directory> \
  --regression-reference <regression-directory>
```

`independent_audit.json` is a complete 14-case audit, not a full-dataset
result. `submission_passed` remains false.
