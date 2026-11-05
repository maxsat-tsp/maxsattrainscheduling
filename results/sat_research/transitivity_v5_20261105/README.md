# Lazy triangle transitivity, round V5

Solver source: `eaf0316`. Full cutoff: 120 seconds.

| Stage / variant | finsteps123 | infsteps180 | cont | Total |
|---|---:|---:|---:|---:|
| screen / Core-orders | 24 | 22 | 18 | 64 |
| screen / Core-orders-transitive | 24 | 22 | 18 | 64 |
| promote / Core-orders-transitive | 24 | 22 | 20 | 66 |
| candidate / AGLR | 72 | 68 | 60 | 200 |

All archived stage audits have an empty error list. Raw schedules,
costs, bounds, process exits and provenance remain in the archive.
The conference reference totals 200 optima; Big-M Gurobi reports 206.
Passing a development or conference gate alone is insufficient to claim SOTA.

Raw SHA-256: `b7c5de3d8e282c3ea8a69af63cc5c3d9c6f280ec92030737d770d654115cad49`.
