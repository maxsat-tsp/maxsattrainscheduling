# Completed trial: no coverage gain

V19 completed all 13 unresolved pairs at 300 seconds, with no new optimum. Native tests passed: 65 Rust and 96 Python; both known-cost smokes and native timeout passed. The raw complete results were independently audited; see `complete_13/` and `validation_snapshot.tar.gz`.

## Original launch record

# V19: queued single-component initial-cost extraction

Source `20e24a9`. The optional flag is false by default. For each visit,
its cost at the propagated earliest entry is unavoidable. Add the sum C0
to LB once and encode f(t)-f(earliest) in CostTree; an incumbent upper bound
U gives a residual objective budget U-C0. Full schedule costs and reported
bounds keep the original objective. This also fixes the documented positive
cost early-return example when the flag is enabled.

Local type checking and 96 Python tests pass. The two new Rust tests cover
an already feasible positive-cost initial schedule and brute-force optima
with sparse costs, objective bounds, hardening, native core minimization,
exhaustion, cycle cuts and both MiniSAT/CaDiCaL. Native execution is pending.

The VM controller waits until V18 finishes, independently audits it, and
proceeds only if V18 has no gains. If V18 has gains it holds for confirmation;
it does not replace them with another candidate. Only then does it run all
Rust/Python tests, build a fresh release, validate known cost 5526 and native
timeouts, and screen the 13 V17 unresolved pairs. Cycle cuts stay disabled,
so the only algorithmic change against V17 is the initial-cost extraction.

The whole service including waiting/build is capped at six hours. Performance
cases are serial at 300 seconds, 6,000,000 KB and CPU group 0,1,4,5. Completed
V17 results and baselines are reused; gains still require confirmations and
regression. A launch or passing tests is not a performance result.
