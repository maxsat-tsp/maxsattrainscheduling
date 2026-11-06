# Common 300-second difficult-instance comparison

`plan.json` freezes 31 pairs: no finsteps123 cases, five infsteps180 cases,
and 26 cont cases. This is the union of failures in the existing focused
selection and the four published 120-second baseline tables.

All five methods rerun exactly the same pairs at 300 seconds:
Orders-Transitive, CSOnet, MaxSAT-Journal, Big-M Gurobi and Big-M CPLEX.
The candidate uses the V5 transitivity method with legacy assumptions,
MiniSAT, no objective bound and no hardening. CPLEX uses the eager Big-M
exporter, four threads and zero relative/absolute optimality gap.

Cases run sequentially, with a deterministic shuffle of pairs and methods.
Each round lasts at most six hours. Resume the same RUN_ID with the same
source, binaries, plan, dependencies and machine. Completed cases are audited
and reused; any invalid schedule, conflicting optimum or fatal process error
stops the round. An interruption does not authorize replacing a failed result.

Report coverage and PAR-2 only for completed comparable pairs at 300 seconds.
The old 120-second tables select cases and provide historical context; their
runtime never enters the new ranking. The report always requires full
validation before a submission claim. Running the difficult subset cannot
establish coverage on the unrun full dataset.
