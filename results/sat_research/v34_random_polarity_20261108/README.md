# V34: MiniSAT random-polarity wrapper (2026-11-08)

The solver exposes `--maxsat-ladder-sc-backend minisat-random-polarity`, backed by satcoder's deterministic literal-hash polarity wrapper. A local adapter records the backend signature and keeps the existing DDD interfaces unchanged. The easy smoke case returned `cost=lb=ub=11`.

The 13 V17 unresolved pairs were measured at 300 seconds. All 13 are valid timeouts and none produced a new optimum. Coverage remains `(72,68,63) = 203/216`. The alias is retained for reproducible ablation, but it is not a journal candidate.
