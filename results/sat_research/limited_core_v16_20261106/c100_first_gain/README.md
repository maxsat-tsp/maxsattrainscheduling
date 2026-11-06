# C100 also recovers origB11/cont

The six-case C100 snapshot captured at 17:22:31 UTC on 2026-11-06 passed
independent local audit, including the native conflict budget and per-case
source/binary provenance. `origB11/cont` has a valid schedule and
`cost=lb=ub=75494`, proved in 114.709866825 seconds. The other five captured
cases are valid timeouts. Nine cases of this profile remain unmeasured in
this snapshot.

The same case took 153.391099899 seconds in the C1000 profile, whereas the
old Orders-Transitive candidate timed out at 300 seconds. These are parameter
screening measurements on separate physical core groups. CSOnet and
MaxSAT-Journal already solved the instance; this is not a new SOTA claim.
Finish both profiles before selecting one and confirming its gains three times.

The raw archive and per-file checksum index are preserved. Its SHA-256 is
`4e91a608327cd32817c4f406d04a5389ed95f21f5adc88c5eeb947e41e7d0319`.
Audit using `audit_targeted_core_minimization.py audit` and the original
completed V14 reference. `independent_audit.json` remains `complete=false`
and `submission_passed=false`.
