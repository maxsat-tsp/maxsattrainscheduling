# V9 rejected; V10 independently audited

All trials used the frozen 18 objective/instance pairs at 120 seconds.

| Trial | Source | infsteps180 | cont | Decision |
|---|---|---:|---:|---|
| V9 temporal-cycle cuts | bd34db4 | — | — | Rejected: invalid schedule on stationB1/cont |
| V10 full assumptions | a51fd80 | 0/4 | 0/14 | No full campaign |
| V10 geometric assumptions | a51fd80 | 0/4 | 1/14 | No full campaign |

The V9 audit failed; repeated runs produced both invalid and valid outcomes.
The precise cause was not isolated. Commits `3706c5e` and `d1d1d6e` reverted
the experiment. Its data are retained to diagnose the failure, and must not
be used for a performance or correctness claim. The archive includes the
resume attempts and original `.previous-*` records where preserved. It is
not an immutable first-run dataset for V9.

Both V10 campaigns passed a fresh independent local schedule audit; their
focused comparisons were regenerated from JSON and matched the VM reports.
Neither increased coverage. `finsteps123` was explicitly skipped.

Archive SHA-256:
`50c87c8eaafc37adf0e450fbfdc0f329df6ee027c3f5d2bd5962f4e421efca6d`.

The next experiment increases the common timeout for the candidate and all
four baselines. No 120-second timeout is relabelled as a 300-second result.
