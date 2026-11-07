# V16 regression: 15 retained, stationA9 lost

All 16 completed regression cases were downloaded. The file checksum index,
source parameters, binary identity, dataset, schedules, costs, runtime
statuses and outcome ledger were independently audited. The data audit
passes. The zero-loss performance check does not pass.

`stationA9/cont` timed out at 300.0104 seconds, whereas the prior candidate
proved cost 7,655. The remaining 15 cases retained their original optima.
No invalid schedule, inconsistent optimum or fatal solver status was found.

The complete C100 development evidence now covers the same 31 difficult
pairs: its first 15-case trial and these 16 disjoint regression cases.

| Method | Rounded / 5 | Continuous / 26 | Total / 31 |
|---|---:|---:|---:|
| Prior Orders-Transitive | 1 | 15 | 16 |
| CSOnet | 1 | 15 | 16 |
| MaxSAT-Journal | 1 | 16 | 17 |
| C100 after regression | 1 | 16 | 17 |

C100 gains origB11 and stationB12 but loses stationA9. This is a net gain
of one relative to its parent, and a tie with MaxSAT-Journal on this set.
`coverage_31.json` retains the exact objective-specific case universe.
Timing conditions of parameter screening and regression remain separate;
this folder does not claim full-dataset coverage or a submission pass.

Archive SHA-256:
`c96e40c0f8eb61c4974f87d6cf0f615ed8f0ccd0a2590ef790683d18dcb9eb21`.
`core_regression_reference.audit` reproduces the audit against the original
V14 reference and selected C100 profile. V17 includes stationA9 alongside
the other unresolved cases, with hashes of this regression locked in its
selection manifest.
