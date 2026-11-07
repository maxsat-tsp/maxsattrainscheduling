# V24: full cost assumptions with the frozen canonical-master binary

V23 passed 77 Rust and 107 Python tests but stopped at known-cost validation:
origA1/finsteps123 proved cost 11 in 27.7777 seconds; infsteps180 was a valid
30-second timeout. No V23 hard case ran. Canonical cost levels cut the number
of new rounded-objective time points, but legacy assumption regrowth still
produced 107,546 SAT calls in that 30-second smoke.

V24 changes only assumptions=full and reuses the exact V23 binary. Solver
source remains d8e2509; runner source is 080edb7. The runner keeps both commits
and the build hash. 108 Python tests and all three known-optimum smokes must
pass, followed by a native timeout probe, before screening 13 hard pairs.
There is no new performance result in this launch note.

The round is serial on CPU group 0,1,4,5, 300 seconds and 6,000,000 KB per
case, with a six-hour total cap. Gains automatically require three repeats
and regression on the 203 solved V17 pairs before a full-coverage claim.


The controller stopped at real-case validation before the hard-case screen.
See stopped_validation/independent_audit.json and its raw archive for the
completed smoke records. No unresolved-case coverage result is claimed.
