# Completed V27 seeded-cost screen: 0 gains in four rounded cases

The four unresolved infsteps180 pairs all timed out validly at 300 seconds;
independent audit recomputed the objective filter, raw hashes, build and
provenance. No panic or invalid schedule occurred, but no new optimum was
proved. The followup is empty and submission_passed remains false.

The seed component was exercised in the known-optimum smokes: 5,870--5,921
seed clauses and 50--4,932 seed points. These tiny smoke runtimes do not
predict hard-case coverage. raw_snapshot.tar.gz is indexed by snapshot.json;
auxiliary.tar.gz retains native tests, build, validation, probe and followup.
Diagnostics are stdout lower/upper bounds only. V27 failed to improve the
best full table, so V28 backend screening remains a separate diagnostic.
