# Hard-set follow-ups, 8–9 November 2026

Downloaded the original VM JSON, logs, launch manifests and campaign files.
`raw_snapshot.tar.gz` preserves their bytes; `archive_hashes.json` records
the archive and independent report hashes. No result was edited to pass audit.

| Experiment | Completed pairs | New proven optima |
|---|---:|---:|
| Adaptive AGLR control | 13 | 0 |
| Adaptive AGLR rescue-model | 13 | 0 |
| Adaptive AGLR duplicate filtering | 13 | 0 |
| Adaptive AGLR heuristic period 8 | 13 | 0 |
| V17 core minimization checks 8 | 13 | 0 |
| V17 core minimization checks 16 | 13 | 0 |
| V17 core exhaustion checks 8 | 13 | 0 |
| V17 core conflict budget 200 | 13 | 0 |

All included runs use MiniSAT and a 300-second internal cutoff. One
AGLR period-8 pair hit the outer timeout (330 seconds, exit 124). It is
counted as unsolved, with matching launch settings and elapsed-time evidence;
an explicit telemetry mismatch is still an audit error.

The attempted `unlimited-mincore` configuration returned exit 101 before
solving: core exhaustion requires a positive conflict budget. It is preserved
for diagnosis and **excluded**, never counted as a valid timeout. Three valid
legacy configurations were unnecessarily repeated by the old restart setup.
This archive uses their first complete run; repeats are not extra independent
instances. The eight-check setting also repeats the previous V35 idea.

The strongest fully audited SAT configuration remains **V17 (72,68,63),
203/216 at 300 seconds**. The projected total in a hard-set report is not
measured full coverage of that new configuration. Previously solved cases
have not been revalidated for these variants, and no SOTA or submission
success follows from this archive. CPLEX and Gurobi results at a different
cutoff are not directly ranked against these 13-pair trials.

To reproduce the independent audit, unpack the archive into a new directory
and run, for each included variant:

```bash
python3 quick_scripts/analyze/audit_aglr_hardset.py \
  --variant /path/to/unpacked/<campaign>/<variant> \
  --reference results/sat_research/core_exhaustion_v17_20261107/full_216 \
  --timeout 300
```

The next trial changes only assumption scheduling (`full` or `geometric`)
on the original V17 binary and the 13 unresolved pairs. It runs from a
pinned worktree, with a fixed run ID, cached timeout results and a persistent
six-hour deadline. Errors stop the round for diagnosis instead of restarting
all variants indefinitely.
