# V17 queued: bounded RC2 core exhaustion

Source and runner: `43cae7674338e0468db1c7be04c446cddb983eef`.
The service `maxsat-core-exhaust-v17.service` began waiting at
17:46:37 UTC on 2026-11-06 (00:46:37, 7 November in Vietnam).
It runs under `tuyenkv`, in a separate worktree:
`/home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling`.
The exact controller and validation scripts are retained beside `queue.json`.

The only new algorithmic component is up to four extra cardinality-floor
checks per newly processed RC2 core. If the hard formula cannot satisfy
`violations <= b`, a validated UNSAT proof permits charging one additional
minimum core weight and raising the floor to `b+1`. SAT or UNKNOWN retains
the last proved floor. Every query uses the selected V16 conflict budget
and the remaining global instance deadline. Main SAT queries keep their
existing conflict-budget behavior. The default flag is zero, preserving
the historical baseline path.

This optimization follows the core-exhaustion mechanism documented by
[PySAT RC2](https://pysathq.github.io/docs/html/api/examples/rc2.html#pysat.examples.rc2.RC2.exhaust_core).
The implementation and weighted-cost identity were checked with actual
MiniSAT on exhaustive Boolean assignments up to five inputs. The local
native harness passes 14 tests; 85 Python tests pass locally and on the VM.
Full Rust library tests and the three schedule smokes are **pending** on the
VM. They are mandatory gates in the controller before any development case.

The controller waits for both V16 profiles and their confirmation service
to finish successfully. V16 gains must reproduce all three times. It then
tests/builds the new release, checks tiny schedules against cost 5526, and
checks native timeout handling on `stationA11/infsteps180` at two seconds.
Because C1000 has now gained two cases, validation also reruns the selected
V16 configuration on the 16 difficult pairs solved by the old candidate.
Their schedules and costs must be retained before any V17 development case.
The original V16 binary is used for this regression, with its recorded CPU
assignment, 300-second cutoff and RAM limit. These are candidate regressions;
the baselines are reused. Raw results go to
`results/aglr/core-v16-regression-selected/` in the V17 worktree.
The previous V16 binaries remain untouched. Release-only compilation saves
space on the VM; at least 2.5 GB must be free before building.

After validation, it chooses one V16 profile by gained coverage then total
PAR-2, retains its settings and only enables four exhaustion checks. Only
that profile's remaining unresolved pairs are measured. Both complete V16
manifest/report hashes are locked, and an independent auditor rebuilds the
selection. No baseline or already confirmed gain is rerun in this screening
trial. The audit CLI accepts `--previous-trials` to verify the source chain.

The instance cutoff is 300 seconds, each case has a 6,000,000 KB address-space
limit, and the solver uses CPUs `0,1,4,5`. Cases run sequentially after all
earlier services finish. The whole controller, including waiting and build,
is limited to six hours plus systemd's 30-second termination grace.

The prepared validation script was amended while the controller was still
waiting, to insert that regression gate after the second V16 gain. Both the
initial and amended scripts and their hashes are preserved. No executing
solver, binary or source worktree was changed by this amendment.

There is no V17 performance result yet. The queue is not a successful
experiment or a submission pass. Read the actual service, validation files
and result audits before updating that status. Manuscript Abstract, Results
and Conclusion have not received provisional numbers.
