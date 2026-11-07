# V31: disable core exhaustion on the V17 hard set (2026-11-08)

This ablation kept the V17 resource-order, transitivity, MiniSAT, core minimization and 300-second settings, but set `core_exhaust_checks=0`.

The 13 pairs unresolved by V17 were all measured and independently audited. Every record is a valid 300-second timeout; no new optimum was proven. Coverage remains `(72,68,63) = 203/216`. The ablation is retained for diagnosis only and is not a candidate for the journal result.
