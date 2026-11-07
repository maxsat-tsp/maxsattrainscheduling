# V29: verified objective bound with V17 transitivity (2026-11-07)

This targeted experiment enabled the already tested verified objective bound together with the V17 resource-order and transitivity settings. MiniSAT 2.1.0 ran on the 13 pairs unresolved by V17 at a 300-second cutoff. A known easy smoke case was checked first and returned `cost=lb=ub=11`.

The hard-set run completed 13/13 valid records, all timeouts, with no newly proven optimum. Coverage therefore stayed `(72,68,63) = 203/216`. The result is archived for ablation only; it does not replace V17.
