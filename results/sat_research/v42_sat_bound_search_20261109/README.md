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
