# V21: full cost assumptions with the frozen V20 binary

V20's first unresolved case times out with 40,606 native SAT calls,
4,155 graph checks and 4,081 learned path cuts. The V17 reference used
1,542 SAT calls on that pair. Graph separation itself takes only 1.613 s.
This motivates a single configuration contrast: send all current cost
assumptions instead of regrowing blocks of 20 after each new refinement.
An older full-assumption trial failed on the old encoding; its data remains
preserved. The present trial tests the changed path-propagation workload.

No Rust algorithm or binary is changed. Solver source stays `8898caf`;
runner source is `4b4d80f`. Binary SHA-256:
`b888e424572ad22cfa145a8f57381eab9354e81a2dcd13b059bb8564535bf340`.
The runner checks this against the V20 build manifest and records the
actual solver and runner commits separately. V20's 73 native Rust tests
remain applicable. The current runner must pass 99 Python tests and both
known-cost strategy smokes plus a native timeout probe before screening.
The full-assumption smoke must report zero partial SAT calls.

Only 13 unresolved V17 pairs are screened at 300 seconds, 6,000,000 KB.
V21 uses disjoint physical CPU group 2,3,6,7 while V20 uses 0,1,4,5.
Timings during overlap are diagnostic; the final full dataset is serial.
The service is capped at six hours. Any gain still needs confirmations and
regression before changing the best complete coverage, currently 203/216.
