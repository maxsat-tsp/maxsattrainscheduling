# V23: canonical objective thresholds in the order master

Source `d8e2509` adds one optional flag to V22: use the earliest allowed
time with the cost of a proved path bound, rather than arbitrary times
inside that cost plateau. For aimed=0, rounded times 200 and 280 both
use the threshold 181 for cost 2. The path proves the representative bound,
and its objective cost is exactly unchanged. The binary-search helper uses
the original monotone objective, clamps to hard earliest and checks i32 edges.
Continuous positive-cost thresholds are unchanged. RC2 settings and the
legacy assumption schedule remain fixed to isolate the representation change.

77 Rust and 107 Python tests pass natively. Master tests compare canonical
thresholds off/on and brute-force optima with both SAT backends; kernel
tests exhaust small cost plateaus and integer-boundary cases. V22 validation
records are preserved separately: no V22 hard case was run after its
rounded-objective smoke timed out at 30 seconds.

V23 must pass all three known-optimum real-instance smokes, alias and
native timeout checks before screening 13 unresolved pairs. It uses an
isolated source tree and release binary. The service's total six-hour cap
includes build, validation, screening and optional followup. Cases use
300 seconds, 6,000,000 KB and serial CPUs 0,1,4,5. Gains automatically
receive three repeats, then 203 solved-pair regressions only if all gains
reproduce. All raw results and losses are retained. Full-table construction
and submission claims remain separate; the best complete result is 203/216.


The controller stopped at real-case validation before the hard-case screen.
See stopped_validation/independent_audit.json and its raw archive for the
completed smoke records. No unresolved-case coverage result is claimed.
