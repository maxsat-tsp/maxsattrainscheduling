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
