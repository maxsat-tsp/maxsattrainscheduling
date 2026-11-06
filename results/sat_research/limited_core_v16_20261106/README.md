# V16: bounded core reduction on 15 unresolved pairs

Both parameter trials use source commit
`57aa220e8abfcf392c6fb41620938e5fa51b5924` and binary SHA-256
`f0bb18ba21efd5b3e6b6dd11b5508ffab237fd7ea6e28593938e586127862e30`.
The complete build and launch manifests are retained in `launch.json`.

| Profile | Extra checks per core | SAT conflicts per extra check | Logical CPUs | Started UTC, 2026-11-06 |
|---|---:|---:|---|---|
| C1000 | 4 | 1,000 | 0,1,4,5 | 16:40:53 |
| C100 | 4 | 100 | 2,3,6,7 | 16:53:12 |

Each profile has two separate physical CPU cores, a 6,000,000 KB address-space
limit per case, a 300-second instance timeout and a six-hour round limit.
The two profiles run concurrently. Do not use their timings as sequential
confirmation measurements.

The native MiniSAT adapter interrupts an ongoing SAT query when the instance
deadline expires. Only additional core-reduction checks have a conflict
budget. An inconclusive check retains the last proved core; it never
authorizes a deletion. The budget is a search-work limit, not milliseconds.
Main SAT calls have no per-query conflict budget. Historical default MiniSAT
dispatch is unchanged.

Validation on the VM passed 54 Rust library tests and 69 Python tests.
Three tiny schedule configurations returned optimum 5526. The previously
problematic `stationA11/infsteps180` returned a valid timeout and exit code 0
at a two-second test limit, with the native deadline flag set.

The reference is the completed, independently audited 186-case backend
comparison in `../backend_comparison_20261106/complete_186/`. Its timings are
reused unchanged. No baseline is rerun. Both profiles run the same selection:

- `finsteps123`: none.
- `infsteps180`: trackA11, trackA12, stationA11, stationA12.
- `cont`: origA8, origB11, trackA8, trackA11, trackA12, stationA1,
  stationA2, stationA8, stationA11, stationA12, stationB12.

`launch.json` records progress only at the capture time. Read the active
service, `failure.json` and `core_minimization_audit.json` together for the
current state. A report written after a valid case can precede a later
failure. This folder is launch evidence, not a completed-result artifact.

Previously solved cases are not measured in this selection. Any gain must
be independently audited, confirmed three times and followed by regression
checks before a full evaluation. Do not merge the best cases of C100 and
C1000 into the result of a single configuration. Submission has not passed.

A partial independently audited capture is in `progress_6_3/`. C1000 has
recovered `origB11/cont` relative to the old candidate, but this case was
already solved by CSOnet and MaxSAT-Journal.

`confirmation_queue.json` and `run_confirmation_after_trials.sh` record the
queued follow-up. Service `maxsat-core-v16-confirm-v2.service` began waiting
at 17:19:10 UTC on 2026-11-06 under user/group `tuyenkv`. It waits for both
parameter services to finish successfully, independently audits both complete
trials, chooses one profile by gained coverage then total PAR-2, and runs
three sequential repeats of its gains using the same binary. The entire
controller, including waiting, has a six-hour limit. The confirmation runner
passed all 82 Python tests on the VM and lives in a separate pinned worktree.
The initial queue service omitted its user identity and failed before any
SAT run; that startup failure is retained in the queue metadata. The second
service uses the same account as the parameter services.
