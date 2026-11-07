# Corrected CPLEX Big-M domain validation

The exporter no longer uses 43,200 seconds as an absolute time upper bound.
It computes an instance-specific disjunction coefficient from release times
and total route travel; time variables remain lower-bounded only. Three native
exporter tests pass, including a late conflicting pair. With CPLEX 22.2,
trackA1/finsteps123 proves 23 and stationB12/infsteps180 proves 98 at 120 s;
independent validation confirms cost=LB=UB and valid schedules. This is a
correctness regression sample, not a complete CPLEX baseline table or a
submission claim. Earlier invalid-overlap and failed-test runs remain on the
VM under cplex-domain-preflight-failed and are not mixed into this archive.
