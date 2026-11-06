# C100 complete: two gains, selected for confirmation

All 15 cases passed independent local audit after download. There are two
new optima relative to the old Orders-Transitive candidate, four valid
rounded-objective timeouts and nine valid continuous-objective timeouts.

| New candidate optimum | Cost = LB = UB | C100 seconds | C1000 seconds |
|---|---:|---:|---:|
| origB11 / cont | 75,494 | 114.7099 | 153.3911 |
| stationB12 / cont | 16,909 | 0.7467 | 34.5859 |

Both profiles gain the same two instances. C100 has lower total PAR-2 and
was selected by the existing selection rule. The confirmation service
started on 2026-11-06 at 18:00:41 UTC, using the original V16 binary. It
runs each selected gain three times, sequentially. The six outcomes have
not yet been confirmed in this artifact.

These are first-run screening timings. The stationB12 difference is large;
both profiles had zero inconclusive extra checks on that instance. It
cannot be explained by the conflict cap alone from these measurements.
The code sorts assumptions by weight without breaking equal-weight ties;
their initial order comes from a randomized HashMap. This provides one
possible source of variation, alongside asynchronous heuristic timing.
The confirmation results must retain their complete timing distribution.

For stationB12, the C100 schedule has been independently checked against
the input, cost and both bounds. Process wall time is 0.769 seconds; the
reported solver time is 0.7467 seconds. It removed 1,116 core literals and
finished with 8,247 variables and 18,697 clauses. These statistics describe
this measured run rather than a general speedup guarantee.

Archive SHA-256:
`ebaad7c6f825179f9df33045a386a96933b66b7df47fe3989abf50f9eea9a1b3`.
The immutable archive, per-file checksum index, independent audit and CSV
are retained here. Regression on the old candidate's 16 solved difficult
pairs is queued before V17. No full-dataset coverage or submission pass is
claimed by this 15-pair profile.
