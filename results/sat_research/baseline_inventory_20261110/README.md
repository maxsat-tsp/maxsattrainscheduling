# Existing Gurobi coverage and missing 300-second observations

This is a read-only inventory of existing Gurobi results. Every available
schedule is independently checked and an optimum requires status ok and
matching cost/LB/UB. Only completed entries in archived audit reports are
imported. A proof is counted at cutoff T only if its reported total_time
is at most T; a short timeout remains missing at a longer cutoff. Repeated
sources never count an instance twice. No paired runtime claim is made.

| Cutoff | finsteps123 | infsteps180 | cont | Total | Missing observations |
|---|---:|---:|---:|---:|---:|
| 120 s | 72 | 67 | 67 | 206 | 0 |
| 300 s | 72 | 67 | 68 | at least 207 | 6 |

The six missing 300-second observations are infsteps180 trackA11, trackA12,
stationA8, stationA11, stationA12; cont stationA12. The baseline is therefore
a lower-bound inventory at 300 seconds, not a completed uniform-run table.
All Gurobi proved costs shared with V42 agree. Do not claim SOTA from
beating 206 while these longer-cutoff results remain incomplete.

The original finsteps123 JSON is preserved here; the other two full-120
sources remain in the V39/V40 result directories. `gurobi_inventory.json`
freezes all source hashes, records, proof sources and the missing-case list.
The author accepts equivalent hardware and minor source-version differences
for reuse. This does not turn historical runtimes into paired measurements.

The six-case completion service waits for V43's terminal marker. It reuses
the ordinary V39 binary whose hash/source are recorded in V39 native build
evidence (the Big-M implementation is unchanged from the full-120 source).
Runner and binary commits are recorded separately. It runs three cheap
native smokes, then exactly those six cases sequentially at 300 seconds
and 6,000,000 KB; results and receipts are preserved. Each controlled round,
including waiting, has a six-hour limit. The inventory is merged only after
independent audit. A final V43 bound report is rebuilt against these new
observations in a new pool; the original frozen pool is preserved.

Rebuild the inventory from the repository root:

```bash
python3 quick_scripts/analyze/inventory_gurobi_reference.py \
  --reference-json finsteps123 results/sat_research/baseline_inventory_20261110/gurobi_finsteps123_source.json \
  --reference-json infsteps180 results/sat_research/v40_sat_bound_search_20261109/gurobi_infsteps180_source.json \
  --reference-json cont results/sat_research/v39_bound_diagnostics_20261109/gurobi_cont_source.json \
  --extended-archive results/sat_research/extended_300_20261106/progress_82/raw_snapshot.tar.gz \
  --extended-archive results/sat_research/cadical_300_20261106/minisat_diagnostic/raw_snapshot.tar.gz \
  --cutoff 300 --output /tmp/gurobi_inventory.json
```

The archive name mentioning CaDiCaL is historical; only its completed
Gurobi entries are imported. No new CaDiCaL experiment is scheduled. CPLEX
still needs a complete audited comparison at the longer cutoff before a
submission-wide MILP dominance claim can be made.
