# V30: deterministic RC2 assumption tie-break (2026-11-07)

The solver now orders equal-weight RC2 assumptions by literal value after sorting by descending weight. This removes dependence on `HashMap` iteration order while preserving the objective and proof rules. Two smoke runs on `origA1/finsteps123` returned identical cost, bounds, SAT calls, variables and clauses.

The 13 V17 unresolved pairs were then run with MiniSAT at 300 seconds. All 13 completed as valid timeouts, with no new optimum; coverage remains `(72,68,63) = 203/216`. The code change is retained for reproducibility, but this round is not a performance gain.
