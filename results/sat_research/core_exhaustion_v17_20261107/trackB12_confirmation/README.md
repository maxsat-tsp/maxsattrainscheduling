# V17 trackB12/cont: three-repeat confirmation

This is the one case gained over MaxSAT-Journal on the complete 31-pair
MiniSAT comparison at 300 seconds. The V17 binary and configuration stay
unchanged; only the independent runner has advanced. It repeats that exact
candidate three times and requires a valid schedule with cost=LB=UB=15182.

The repeats use physical CPU group 2,3,6,7 while V18 screening uses the
disjoint group 0,1,4,5. Each case has 6,000,000 KB; the entire confirmation
service is capped at 20 minutes. Timings are diagnostic and are not mixed
into final sequential PAR-2. All three repeats are now complete and independently audited.
See `manifest.json`, `confirmation_audit.json`, `independent_audit.json` and the raw archive.
The three valid costs all equal 15182, with runtimes 10.6501, 4.6406 and 11.8576 seconds.
Median: 10.6501 seconds. This confirms this one V17 gain, not all changed cases.
