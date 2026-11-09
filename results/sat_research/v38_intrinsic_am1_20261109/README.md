# V38: bounded intrinsic-AM1 adaptation, launch snapshot

The new component starts from a proved two-preference core and extends it
only after SAT proves incompatibility with every existing group member.
At most 16 pair queries are allowed per attempt, each capped at 100 native
MiniSAT conflicts. Only residual Primary preferences are reweighted;
RC2 totalizer preferences keep their existing handling. An adaptation is
accepted only when its fixed cost exceeds the seed core's minimum weight.
The weighted AM1 identity follows the standard RC2 process, not a new
standalone contribution: [PySAT reference](https://pysathq.github.io/docs/html/api/examples/rc2.html#pysat.examples.rc2.RC2.process_am1).

Source is pinned at `6acd6c9`. `am1_checks=16` is enabled on the V17
configuration with the V30 deterministic tie ordering retained. V37
trimming is disabled. Only MiniSAT is used; all 13 V17-unsolved pairs
have cutoff 300 seconds, RAM 6,000,000 KB and serial CPU affinity 0,1,4,5.

Native VM validation passed three AM1 algorithm tests, two integration /
exhaustive scheduling tests, 129 Python tests, six real-case smoke runs
with the feature enabled/disabled, and a deadline probe. All six smoke
schedules and recorded Rust source hashes were independently verified
after download. The launch archive contains raw evidence; the binary
itself is identified by its hash rather than included.

The smoke runs and short deadline probe exercised pair queries but did
not find a larger AM1 group. They validate the guarded execution path;
they do not demonstrate a stronger bound on this dataset. The exact
AM1 reweighting is separately exercised by the native SAT truth-table
test. Any later gain with zero adapted groups must not be attributed to
the group rewrite without an ablation of the extra SAT queries.

The hard-set trial is running; **no new coverage or SOTA claim is made**.
The best audited full SAT result remains V17 (72,68,63) = 203/216.
Service `maxsat-intrinsic-am1-v38.service` uses a fixed RUN_ID, frozen
worktree, hashed binary, cached completed timeouts and a six-hour wall
limit. Gains trigger three confirmation runs and regression before review.
