# V42: RC2 warmup then SAT search under one shared deadline

Frozen source: `c53cd29`. The only algorithm change from V41 is a uniform
RC2 warmup of at most 60 seconds, included in the instance's total 300
seconds. Both phases use MiniSAT. If RC2 proves an optimum, return it;
otherwise hand its already proved LB and checked incumbent to V41's
close-upper SAT search. Native UNKNOWN never raises a lower bound.
No reference cost/schedule enters the optimizer. The default warmup is
zero, preserving the earlier solver path.

## Native preflight and first independently checked case

Native checks passed: 10 search/exhaustive tests, 1 RC2 checkpoint test,
1 legacy-vs-enumeration test, 5 binary objective tests, 173 Python tests,
three real-case smokes, a shared-deadline probe and a forced RC2-to-SAT
handoff probe. After download, all 56 Rust file hashes were checked against
the frozen source; receipt hashes, schedules and both phases' bounds were
independently replayed.

The first hard case restores `infsteps180/stationA8`, lost by V40/V41:
**cost=LB=UB=161 in 35.202701 seconds**. RC2 itself proves the optimum
within its 60-second warmup (35.189654 seconds); no SAT threshold query is
needed. The initial bounds are calculated from input/greedy data, not
copied from V17's already known optimum 161. This is a restored proof,
not a new best known objective value.

The next phase tests exactly the twelve unresolved pairs in the full V41
archive, whose source and SHA-256 are locked in the campaign manifest.
The optimizer receives only an instance, objective, timeout, threshold
policy and warmup duration. The archive is used by the runner to select
cases and by the auditor after execution. No origA8/stationA2 rerun is
scheduled in this hard phase. A new gain triggers three confirmations
and actual regression on the 204 V41-solved pairs, within six hours.

This snapshot contains native preflight plus **one of twelve hard cases**.
The full campaign is pending. Do not add the restored case to 204 and
claim 205/216 before confirmations and regression have completed. No
submission/SOTA claim is made.

- `partial_snapshot.tar.gz`: preflight, build/dependency hashes, smokes,
  deadline/handoff probes, manifests and the completed case only; excludes
  executable and still-running case files.
- `validation_audit.json`: source/receipt and native preflight validation.
- `independent_audit.json`: replay of the completed hard case, 1/12.
- `priority_evaluation.json`, `reference_pool.json`, `.sha256`: frozen
  coverage/bound comparison, including known V40/V41 and MILP bounds.
- `archive_hashes.json`: hashes of accompanying artifacts.

VM root:
`/home/tuyenkv/projects/sat-bound-search-v42/results/aglr/sat-bound-search-v42-20261109/`.
Services: `maxsat-sat-bound-search-v42.service` and the separate read-only
`maxsat-bound-priority-report-v42.service`. The latter uses idle CPU cores
and updates the reports under `evaluation/` every minute. The full report
compares the new method with V41, then records bounds relative to all
imported methods. Missing/unfinished cases cannot pass the full gate.

## Complete round, independently audited 10 November

All twelve hard cases, three confirmations and 204 regression cases have
completed successfully. `complete_snapshot.tar.gz` preserves the unmodified
full VM campaign. `full_evaluation.json` rechecks every schedule/cost and
replays both RC2 and SAT bound updates, then requires 216 distinct pairs
from the same source/binary/configuration. Coverage is now measured:

| Objective | V17 / 300 s | V41 / 300 s | V42 / 300 s |
|---|---:|---:|---:|
| finsteps123 | 72 | 72 | 72 |
| infsteps180 | 68 | 67 | 68 |
| cont | 63 | 65 | 65 |
| Total | 203 | 204 | 205 |

The restored stationA8/infsteps180 optimum 161 reproduces in all three
confirmations: 34.843569 / 35.281195 / 35.056550 seconds. No previously
V41-solved case is lost. There are eleven unresolved pairs.

V42 also improves the best imported UB for infsteps180/trackA11 from 127
to **109**, with an independently checked schedule. Its own LB is 92,
weaker than the previous best 101. Report [92,109] versus [101,127];
[101,109] is pooled knowledge and is not V42's independently obtained
interval. No other unresolved case improves a bound over all imported
SAT/MILP references; two improve a bound relative to prior SAT runs.

Five final UNKNOWN thresholds are below the previously known LB:
trackA11/cont 14694, stationA8/cont 26492, stationA11/cont 14849,
stationA12/cont 15936 and trackA11/infsteps180 100. This motivates testing
UB-1 throughout the SAT phase, rather than only within the 5% gap region.
Reference bounds remain audit-only; that test still computes every target
from its own incumbent.

`full_summary.csv`, `unresolved_bounds.csv` and `full_reference_pool.json`
(with a SHA-256 receipt) accompany the complete evaluation. The earlier
one-case snapshot is preserved unchanged as historical evidence. There is
no SOTA claim: the Gurobi source inventory already contains **at least 207**
proved pairs within 300 seconds, with six remaining cutoff observations
yet to be completed. See `../baseline_inventory_20261110/`.
