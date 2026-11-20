# V45 native validation and initial baseline evidence

On 20 November the VM boot volume was raised from 30 to 50 GiB.
The original IOPS (3180) and throughput (185 MiB/s) were verified after
the cloud update. Ubuntu required online expansion of the root partition
and ext4. Snapshot `trp-before-root-grow-20261120` was ready before that
operation. The expanded root filesystem reported 20 GiB free.

V45 runs from frozen source `14b0df5`. The native preflight archive contains
both assumption modes' three smoke cases, shared deadline probe and forced
RC2-to-SAT handoff, along with the 21 Rust and 193 Python test logs.
`preflight_replay.json` checks 58 Rust file hashes in each manifest and
independently replays the case receipts, schedules, costs and bounds.
The handoff reaches the same `cont/origA1` optimum 5526 in three threshold
decisions in both modes. The rebuild mode creates three SAT models and
reuse creates one.

`sat_baselines120_snapshot.tar.gz` preserves the JSON and configs from
the VM's `full-final-120-20261108` CSOnet and MaxSAT-Journal runs.
`initial_cutoff_comparison.json` verifies the short-cutoff proof counts
and identifies the nine missing 300-second observations for each
solver after reuse of valid historical MiniSAT measurements. Its
candidate is the completed V42 run. The baseline inventory is not
a completed 300-second comparison for those two methods.

VM services `maxsat-sat-bound-search-v45.service` and
`maxsat-cplex-reference-tail-v45.service` run in sequence.
The first measured V45 case started at 14:23 on 20 November (Vietnam
time). At this checkpoint CPLEX was waiting and the full SAT comparison
was pending.

## First hard case

In reuse mode, `cont/stationA1` found a verified schedule of cost 12884
at 245.06 seconds using one SAT model across all six decisions. This
matches the audited Big-M optimum and improves on V43's SAT UB 12934.
The final decision at 12883 returned UNKNOWN, so the solver timed out
with its own interval [12504,12884]. The paired rebuild control and
the other hard cases are still running. The snapshot and independent
audit cover this one completed case.

## Complete comparison at 300 seconds

`matched_snapshot.tar.gz` preserves both finished modes, their native
results and the shared frozen reference pool. `matched_audit.json`
records the independent replay of the 22 cases.

| Mode | Optima on 11 hard cases | First query timed out | SAT models created | Mean remaining gap |
|---|---:|---:|---:|---:|
| Reuse | 0 | 5 | 11 | 39.04% |
| Rebuild with assumptions | 0 | 5 | 27 | 39.87% |

Both configurations improved two SAT-only bounds. Neither improved the
best bounds across all imported methods. On `cont/stationA1`, the final
verified schedules cost 12884 with reuse and 12885 with rebuilding. The
full-dataset SAT reference remains V42 at 205/216.

The first 300-second CPLEX attempt exited in preflight because Git ignored
a historical `cplex.log`. Commit `9481aed` tracks the original bytes
matching the recorded hash. A separate clean worktree validated the
205 reused proofs and started the 11 missing cases. The failed attempt
and the original V45 worktree remain available for provenance.
