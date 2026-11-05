# Orders + sparse costs, 120 seconds

Source commit: `7a1aa6d`. VM round: `maxsat-hybrid-v4-7a1aa6d`.
This adds sparse costs to the previously measured shared-order variant;
refinement and assumption scheduling remain `legacy`.

| Stage | finsteps123 | infsteps180 | cont |
|---|---:|---:|---:|
| Screen, 30 s, 24 instances | 24 | 22 | 17 |
| Promote, 120 s, 24 instances | 24 | 22 | 20 |
| Full, 120 s, 72 instances | 72 | 68 | 59 |

Full PAR-2 from `total_time`: 0.029841471, 14.363712321, 46.920082931 s.
All stages passed independent schedule, cost, bounds, configuration and
process-exit checks. Full coverage is 199, below the published conference
coverage of 200 and Big-M Gurobi coverage of 206. No confirmation repetitions
were started; these results do not justify a superiority claim.

`raw_results.tar.gz` preserves JSON, manifests, per-instance logs and audits.
SHA-256: `452927f37633a39b68951aac6450a89729fcb4a591ff56e849ee1039b64f89eb`.
Runtime comparison assumes equivalent hardware, as agreed by the authors;
the old conference binary/environment has not been independently recovered.
