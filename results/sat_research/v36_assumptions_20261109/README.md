# V36: assumption scheduling on the original V17 binary

Launched on 9 November 2026 with the exact audited V17 binary (solver
source `43cae76`, hash in `launch_audit.json`). Runner source is pinned
at `91a2f6a` in `/home/tuyenkv/projects/v17-assumptions-v36`.

Only `assumptions=full` or `assumptions=geometric` differs from V17.
Resource orders, transitivity, core minimization (4 checks, 100 conflicts)
and core exhaustion (4 checks) stay unchanged. Backend: MiniSAT.
Cutoff: 300 seconds per pair; RAM: 6,000,000 KB; sequential CPU affinity
0,1,4,5. Both variants select the same 13 V17-unsolved pairs.

127 Python tests passed on the VM. Six smoke runs (`origA1`, both strategies,
three objectives) proved costs 11, 34 and 5526. Their raw schedules, launch
manifests and logs are in `launch_snapshot.tar.gz`; all six schedules were
independently verified again after download.

The hard-set trial was still running when this launch snapshot was captured.
**There is no hard-set gain or submission claim in this directory.** The
strongest fully measured SAT coverage remains V17 (72,68,63) = 203/216.

Service: `maxsat-v17-assumptions-v36.service`. A fixed RUN_ID, pinned
worktree, unchanged copied binary, per-case manifests and cached timeout
results prevent the old repeated-run problem. A persistent six-hour wall
deadline applies across restarts. Audit/configuration failures stop with
exit 78 and a `FAILED` marker; they do not start an endless retry cycle.
If a new optimum appears, the controller confirms it three times and
regresses the 203 solved V17 pairs within the remaining wall budget.

## Completed full-assumption trial

`full_complete/` now contains the original 13-pair snapshot, independently
rebuilt audit and telemetry. All 13 pairs timed out validly at 300 seconds;
there is no new optimum. The geometric trial was still running when this
completed full trial was downloaded. No incomplete geometric result is
counted as a full-dataset measurement.

`telemetry.csv` includes the last lower bound printed in each stdout log
for diagnosis only. It is not substituted for an audited proof or a
returned LB/UB pair. The independent audit checks every raw case against
the frozen manifest, original V17 reference and the selected 13-pair scope.

## Completed geometric-assumption trial

`geometric_complete/` contains all 13 original geometric results and the
independently rebuilt audit. All 13 timed out validly, with no new optimum.
Both V36 variants are now complete; neither changes the V17 coverage.
