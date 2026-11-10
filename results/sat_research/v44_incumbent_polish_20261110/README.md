# V44 queued: improve own SAT incumbents within the same deadline

Frozen source `6a67a14`. Installed and enabled on the VM at 03:37:40 UTC
on 10 November. The service is **waiting**, not measuring yet: its root
contains only the campaign lock and fixed six-hour deadline. It waits for
terminal markers and inactive solver services for both V43 and its Gurobi
tail before any build, tests or benchmark.

Compared with V42, the single method change is polishing each returned SAT
witness: retime fixed resource orders, try bounded adjacent swaps, verify
each accepted schedule, and keep only lexicographic improvements of
(objective cost, continuous delay). Default off; V44 uses 4096 neighbor
checks per SAT witness. It preserves close-upper search, MiniSAT, RC2
warmup at most 60 seconds included in a shared 300-second total, 6,000,000
KB RAM and CPU affinity 0,1,4,5. It does not polish RC2 warmup checkpoints
or read external incumbents. No polishing operation proves a lower bound.

Local validation passed 191 Python tests, full Rust test/binary type
checking, Bash syntax and LaTeX compilation (35 pages). Eight new Rust
polisher tests also passed in a temporary native harness importing the
unmodified Problem and polisher modules; this harness does not link SAT or
MIP. **Full VM native preflight is pending** and must pass 27 Rust tests,
191 Python tests, real-case smokes and timeout/handoff probes before any
benchmark starts. See ../offline_incumbent_polish_20261110/local_validation.json.

Hard selection is exactly the eleven unresolved pairs in the checked full
V42 archive. A new optimum triggers three confirmations and actual
regression on the 205 V42-solved pairs. The new pool imports the six
Gurobi observations if their audit has completed. The offline UB 114 is
already known and may not be counted again as a new bound. Frozen older
pools and source data remain unchanged. There is no V44 coverage or SOTA
claim at this stage.

Service: `maxsat-sat-bound-search-v44.service`.
Root: `/home/tuyenkv/projects/sat-bound-search-v44/results/aglr/sat-bound-search-v44-20261110`.
`hard/audit.json` is refreshed after each case; priority evaluations are
written at phase completion. FAILED/INCOMPLETE markers stop the round.
