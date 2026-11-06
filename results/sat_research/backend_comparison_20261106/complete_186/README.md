# Completed comparison: 186/186 independently audited SAT cases

The two-backend trial completed at 15:33:58 UTC on 2026-11-06.
Every schedule/cost audit passes; the 12 cases missing from V13 were run
after the CaDiCaL deadline repair. All 174 earlier valid measurements were
reused unchanged. There are 31 difficult instance/objective pairs, three
methods and two backends. This is not a full 72-instance evaluation.

| Method | Rounded MiniSAT | Rounded CaDiCaL | Continuous MiniSAT | Continuous CaDiCaL |
|---|---:|---:|---:|---:|
| Orders-Transitive | 1/5 | 1/5 | 15/26 | 14/26 |
| CSOnet | 1/5 | 1/5 | 15/26 | 14/26 |
| MaxSAT-Journal | 1/5 | 1/5 | 16/26 | 12/26 |

MiniSAT gives greater continuous-objective coverage for all three methods,
so subsequent core-reduction trials use MiniSAT. Rounded-objective coverage
is tied; CaDiCaL has lower PAR-2 for CSOnet and MaxSAT-Journal. This does not
establish that one backend is fastest for every objective or instance.
PAR-2, medians and gained/lost lists are in the JSON/CSV.

Raw timings retain their original sequential/parallel, binary and RAM
provenance. `backend_parallel_same_binary.csv` restricts the timing cohort
accordingly. Final article timing claims still require confirmation.
The trial does not demonstrate a win over all SOTA baselines.

Archive SHA-256:
`f5ea89c2328f2c42f4e8982a046ee30d93eaa57394b12d657b874ebf0a079082`.
After extraction into a new directory, run:

```bash
python3 quick_scripts/analyze/compare_sat_backends.py audit <directory>
```

The archive includes all completed JSON measurements and their provenance.
It has been independently audited again after download to the local machine.
