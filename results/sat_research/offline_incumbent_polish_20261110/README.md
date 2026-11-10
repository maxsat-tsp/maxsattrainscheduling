# Offline test: retime and improve a SAT solver's own witness

This is a local diagnostic, not a timed autonomous optimizer experiment.
Inputs are already checked V42/V43 SAT witnesses. No MILP schedule, optimum
or reference bound is supplied to the prototype.

Fix the order of visits on each exclusive resource and find the earliest
schedule obeying those orders and train travel times. Then try swapping
adjacent visits, rebuilding the earliest schedule, and keeping the best
strict improvement of (objective cost, continuous delay). Reject cyclic
neighbors. Resource and train orderings have fixed tie-breaking. Every
accepted final schedule is independently checked.

On V42's infsteps180/trackA12 witness, retiming changes cost 123 to 122;
four swaps yield **114**, compared with previously imported UB 118. The
original V42 result is unchanged. This proves a feasible upper bound only:
do not assign the historical LB 106 to this postprocessor or count a new
optimal instance. This observation is registered in future reference pools,
so finding 114 again cannot be counted as a new best bound.

The source archive/member and hashes are locked in `witness.json`;
`compare_search_bounds.py` checks both the source and derived schedules and
imports **UB only**, with no runtime/cutoff or coverage contribution.
`v42_probe.json` and `v43_probe.json` preserve all probe outputs, including
unsuccessful cases. The two Python files are the original local prototypes;
their `/tmp/v42-complete` and `/tmp/v43-progress` inputs are extracted raw
campaign snapshots, and their timings are local diagnostics only.

This motivates testing a native bounded incumbent-polishing step *inside*
the shared SAT search deadline. It does not establish its benchmark gain.
The new native path defaults off and must pass exhaustive/unit/auditor
preflight before a VM campaign starts.
