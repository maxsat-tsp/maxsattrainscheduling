# Common CaDiCaL comparison, separate from the source-aligned MiniSAT baseline

Follow-up verification confirms that CSOnet uses an integrated Rust RC2
optimizer and its available source constructs MiniSAT. The original COR
authors' 2023 preprint explicitly specifies RC2 with MiniSat 2.1.0, and their
public code also constructs MiniSAT. RC2 and the SAT backend are separate
layers. The MiniSAT campaign remains valid source-aligned baseline evidence;
it is not discarded because of its SAT backend. The present CaDiCaL campaign
is an additional controlled backend comparison, not a reproduction of an
established CaDiCaL configuration in either paper. See
`manuscript/journal/reviews/solver_stack_20261106/README.md` for sources.

The student's source at `c427a10` constructs MiniSAT for
`MaxSatDddLadderSc` and the journal MaxSAT-DDD solver. The accepted manuscript
lists RC2 for its MaxSAT configurations and Glucose 4.2 for its SAT methods;
it does not identify RC2's underlying SAT backend. The binary that produced
the published tables has not been identified. Therefore this evidence does
not establish that the conference runs used either MiniSAT or CaDiCaL.

The current experiments had followed the source's MiniSAT constructors.
The legacy `maxsat_ddd_cdc` name was misleading: its constructor went through
a Glucose compatibility alias that resolved to MiniSAT. The new code fixes
that alias and offers an explicit genuine `cadical` backend. Every CaDiCaL
run must record a native `maxsat_backend_signature`; a label alone fails audit.

At the user's request, the new 300-second campaign runs all three MaxSAT
methods with genuine CaDiCaL: Orders-Transitive, CSOnet encoding and
MaxSAT-Journal. It uses the same 31 pairs and unchanged MILP configurations.
Core minimization is off for this comparison, to isolate the backend change.

The previous MiniSAT campaign was stopped with 91/155 completed runs and a
clean audit. Its queued minimization trial was cancelled. The raw completed
snapshot is retained under `minisat_diagnostic/`, SHA-256:
`a66e7ab69f5b9afe387b33d570aee77e33cffb5b7160edb37ad8976c0eac6098`.
The interrupted unfinished case is excluded from that snapshot.

37 completed Gurobi/CPLEX cases can be reused byte-for-byte at the same
cutoff, on the same VM and with identical MILP parameters. All 93 SAT cases
must run again with CaDiCaL; 25 remaining MILP cases also run, for 118 newly
measured cases. The old SAT times remain MiniSAT baseline evidence, not
CaDiCaL results or an exact reproduction of the unidentified conference binary.

The new campaign started on 2026-11-06 at 10:33:20 UTC (17:33 Vietnam),
service `maxsat-cadical300-v12-4a43a9c.service`, source `4a43a9c`.
All 46 Rust library tests and 59 Python tests passed on the VM. All five
methods independently verified optimum 5526 on `origA1/cont`; the three
MaxSAT methods reported native signature `cadical-1.9.5`. See `launch.json`
for binary hashes and the exact result directory. This receipt records the
start of the campaign, not a completed comparison or evidence of a speedup.
