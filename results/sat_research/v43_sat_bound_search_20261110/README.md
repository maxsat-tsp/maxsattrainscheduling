# V43: ask for a strict incumbent improvement throughout SAT search

Frozen source `cc13eb4`; MiniSAT; RC2 warmup 60 seconds included in the
shared 300-second limit. The only algorithm change from V42 is the target
`T = U - 1` at every SAT decision. SAT lowers U using a verified schedule;
UNSAT closes L=U; UNKNOWN never changes either bound. No oracle costs or
schedules enter the optimizer.

Native preflight passed 18 Rust tests (11 search, 5 objective, 1 RC2
checkpoint, 1 legacy/exhaustive), 182 Python tests, three real-case smokes,
a global-deadline probe and a forced RC2-to-SAT handoff. Downloaded results
were independently replayed; hashes of all 56 Rust sources and Cargo.lock
match the frozen commit. Native binary SHA-256:
`01ef16721d25e867c32f996b3c6b4821a9ec9f19918852a906c4b5c3f214c3ea`.

This snapshot contains **two of eleven hard cases**, both timed out:

| Objective / instance | V42 own [LB,UB] | V43 own [LB,UB] | Best imported optimum |
|---|---|---|---|
| cont / stationA1 | [12504,12951] | [12504,12934] | 12884 |
| cont / trackA8 | [20934,30298] | [20934,25043] | 24441 |

These are better UBs than previous SAT results, but neither improves on
the imported MILP optimum. There is no new optimum or global best bound
in this partial snapshot. Do not add partial hard-case results to V42's
205/216 and call that V43 coverage. Any new optimum triggers three
confirmations and an actual regression of 205 previously solved pairs.

`partial_snapshot.tar.gz` contains preflight, build/dependency manifests,
probes, hard manifest and completed case directories only. No binary or
still-running result is included. `validation_audit.json` checks preflight;
`independent_audit.json` replays the two completed cases. The frozen
reference pool and priority evaluation preserve the comparisons.

VM root:
`/home/tuyenkv/projects/sat-bound-search-v43/results/aglr/sat-bound-search-v43-20261110`.
The solver and separate read-only reporter run under systemd. A queued
Gurobi service waits for the SAT terminal marker before running exactly
six missing 300-second observations. Existing Gurobi data already proves
at least 207 pairs at this cutoff; CPLEX also needs complete longer-cutoff
comparison. No SOTA or submission claim is made.
