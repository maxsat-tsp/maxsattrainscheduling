# V40: autonomous SAT search over cost thresholds

The first frozen candidate (`9ab1725`) accepts only an instance, objective,
total time limit and output path. It has no optimum or oracle-schedule input.
MiniSAT, V17 resource orders, transitivity and DDD refinement are retained.
RC2 cost optimization is replaced by binary search over fixed-budget SAT
decisions; each threshold rebuilds the model. All queries share **one
300-second deadline per instance** and the run has a six-hour wall limit.

The initial LB is the sum of visit costs at chain-propagated earliest times.
The UB comes from an independently validated greedy schedule. A SAT witness
updates UB to its checked cost; an UNSAT proof raises LB to threshold+1.
UNKNOWN changes neither bound and stops that instance. Reference costs are
consulted by the auditor only after the solver process exits.

## Independently checked partial results

| cont instance | Result | Seconds | Recorded LB / UB | Threshold queries |
|---|---|---:|---:|---:|
| origA8 | optimum, cost 23143 | 176.520220 | 23143 / 23143 | 14 |
| stationA1 | timeout | 300.001722 | 12729 / 13197 | 6 |

`origA8` is a new autonomous proof relative to the frozen V17 full reference,
whose corresponding run timed out at 300 seconds. V39 also timed out with
both ordinary RC2 and RC2 given the optimal incumbent. The V40 schedule,
every improving schedule in its query ledger, the input-only initial LB,
the full sequence of bounds and the shared deadline were checked again
after download. Recorded Rust source hashes match the frozen commit.

This is **not** a new full-dataset coverage or SOTA claim. The other eleven
unresolved pairs are not present in this snapshot. The VM continues all
13 unresolved pairs; any gain then triggers three confirmation runs and
regression on V17's 203 previously solved pairs. A failed confirmation or
an unfinished regression must be reported before drawing a full conclusion.

Native validation passed five search/exhaustive tests, five binary-cost
tests, 144 Python tests, three real-case smokes (costs 11, 34, 5526) and a
native timeout probe. A subsequent local auditor check also rejects
changed build/source evidence and duplicate campaign tasks. Raw evidence
and frozen build/dependency hashes accompany the independent audit.

`raw_snapshot.tar.gz` contains completed cases only, preflight evidence,
the predecessor audit and manifests; it excludes the executable and active
case files. The binary is identified by SHA-256 in `validation_audit.json`.

The first trace is a useful next-step diagnostic: after SAT found cost
23143, six more bisection UNSAT queries closed the remaining 34-unit gap.
Testing the current UB minus one, or preserving learned model information
between thresholds, are possible later ablations; neither is implemented
in V40 and neither has a measured gain here.

VM service: `maxsat-sat-bound-search-v40.service`.
Root: `/home/tuyenkv/projects/sat-bound-search-v40/results/aglr/sat-bound-search-v40-20261109/`.
