# Corrected CPLEX optimum for finsteps123/trackA8

The old full-120 run reported cost=LB=UB=35, but V17 and V40 independently
validated schedules of cost 34. Rerunning **the exact same LP bytes** with
CPLEX integrality/feasibility tolerances 1e-9, numerical emphasis, zero
relative/absolute MIP gaps and a 120-second cutoff gives cost=LB=UB=34.
The new CPLEX schedule is independently checked and matches its internal
objective. No SAT witness is given to CPLEX; the witness is comparison only.

`raw_snapshot.tar.gz` preserves both the successful `tight_recheck/` and
`rejected_command_attempt/`. The first attempt used numeric `1` for the
interactive numerical-emphasis option, which requires `y`/`n`; it produced
no solve and is excluded. The successful retry is from source `76bff0c`.

`independent_audit.json` reconstructs the successful result directly from
CPLEX XML and log, checks the witness, and compares the LP hash with the
original full-baseline archive. The derived `cplex_csv/` copies all three
72-instance CSVs and changes only finsteps123/trackA8. Its runtime combines
the original measured export time of the identical LP and the new tight
solve time; these remain diagnostic timings. Coverage remains (72,67,66),
205/216. Original JSON/CSV files and the frozen V40 reference pool are
preserved unchanged.

Rebuild from the repository root:

```bash
python3 quick_scripts/analyze/rebuild_cplex_recheck.py \
  --archive results/sat_research/cplex_full_120_20261108/bound_recheck_20261109/raw_snapshot.tar.gz \
  --original-archive results/sat_research/cplex_full_120_20261108/raw_snapshot.tar.gz \
  --reference-csv results/sat_research/cplex_full_120_20261108/cplex_csv \
  --output results/sat_research/cplex_full_120_20261108/bound_recheck_20261109
```

Future reference pools import the strict rerun and explicitly identify
which old bound it resolves. Previously frozen reports retain the old
conflict because that is the evidence available when those pools froze.
