# Verified objective-bound trial, round V6

Source: `6ba1b71`; VM round: `maxsat-bound-v6-6ba1b71`.
The trial adds a bound from verified feasible schedules to shared resource
orders. It retains legacy refinement, assumption scheduling and cost levels.

| Stage | finsteps123 | infsteps180 | cont |
|---|---:|---:|---:|
| Screen, 30 seconds, 24 instances | 24 | 22 | 18 |
| Promote, 120 seconds, 24 instances | 24 | 22 | 20 |
| Full, 120 seconds, 72 instances | 72 | 68 | 59 |

Full PAR-2: 0.034321594, 14.232938927, 47.390598207 seconds.
All stage audits have no errors. Total coverage 199 does not exceed the
conference total 200 or Big-M Gurobi total 206. No confirmation repetitions
were started. These are diagnostic results, not a journal superiority claim.

Raw archive SHA-256:
`4a3e89b109de9757fd2b22f217727779b8c97f980717ba0bdc0aa8b76c691b9e`.
The archive preserves schedules, source/binary/dependency/dataset hashes,
resource limits, per-instance logs and audits. Old reported runtimes are
compared under the authors' equivalent-hardware assumption.
