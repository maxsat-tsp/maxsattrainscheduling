# V33: heuristic submission period 8 (2026-11-08)

This run used the `maxsat_ddd_ladder_aglr` alias with `--aglr-policy legacy`, so the locked telemetry records `aglr_heuristic_period=8` and `aglr_heuristic_min_gap=0`. All other settings match V17: resource orders, transitivity, MiniSAT, core minimization and core exhaustion.

The 13 V17 unresolved pairs were all measured at 300 seconds. Every record is a valid timeout and no new optimum was proven. Coverage remains `(72,68,63) = 203/216`. This is an ablation only; the earlier V32 run is intentionally excluded because its alias ignored the period flag.
