# V20: conditional earliest-time path propagation

Source `8898caf`. V18 and V19 both completed the 13 unresolved V17 pairs
without a new optimum. V20 retains V17's MiniSAT/core settings and enables
only `order_path_cuts=true`; initial-cost extraction stays off.

For each selected resource order, use its true exit-to-entry edge, together
with fixed route edges and hard earliest times. First block a positive
cycle. Otherwise condense zero-weight components and propagate longest
lower bounds in the acyclic component graph. Every propagated value retains
its own immutable path witness. A violated bound learns the disjunction of
negated path guards and the target ladder literal. Prefer objective-cost
increase, then time increase, then visit ID. Add at most one path point per
full model and register its CostTree cost before another SAT call.

73 Rust and 97 Python tests pass natively. They include a 10,000-node chain,
zero cycles, exact exits, exhaustive guarded-schedule checks, and exhaustive
three-train optima that actually trigger path cuts and cost registration
with both SAT backends. Initial-bound options are checked on a separate
fixture with a verified seed. The first pretest failure and its reason are
retained; no performance case ran before the corrected tests passed.

The controller builds a pinned release and validates known optimum 5526
with path cuts off/on and a native timeout probe before screening. Only the
13 unresolved pairs are measured; all previous candidates and baselines
are preserved. Cases run serially at 300 seconds, 6,000,000 KB, CPUs 0,1,4,5;
the round has a six-hour service limit. A gain requires three confirmations
and regression before changing full coverage. There is no V20 performance
claim in this launch record.
