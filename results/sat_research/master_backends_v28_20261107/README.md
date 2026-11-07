# V28: same-binary MiniSAT/CaDiCaL contrast on four unresolved rounded cases

Both profiles reuse the frozen V27 binary (solver source c1b046f) after
its complete audited round. Runner source is 9f32564. Every method flag,
instance, resource limit and per-instance cutoff matches within the pair;
only the SAT backend differs. Each profile has its own raw results and
manifest, a shared paired_run_id, and an explicit paired-screen context.

The MiniSAT-specific 100-conflict cap is not implemented by the CaDiCaL
adapter. Both V28 profiles therefore use core_minimize_conflicts=0
(unlimited conflicts per query), retain four minimization checks, and
disable the MiniSAT-only core-exhaustion path equally (`core_exhaust_checks=0`).
V27 MiniSAT/100 stays separate. V28 MiniSAT/0
isolates the cap change; V28 CaDiCaL/0 isolates the backend against it.
This does not equate an unenforced CaDiCaL cap with an enforced MiniSAT cap.

The two serial-per-backend screens run concurrently on distinct two-core
CPU groups (0,1,4,5 and 2,3,6,7). Each process has 6,000,000 KB RAM and
300 seconds per pair, with a six-hour round cap including waiting. New
gains require three confirmations and the 68 previously solved rounded
pairs. All concurrent screen/followup runtimes remain diagnostic and cannot
enter the main runtime table without a serial rerun. Full coverage and
submission gates remain separate and false.

The controller waits for V27 to stop and independently audits its complete
four-case raw results. Missing/incomplete/invalid V27 evidence stops V28.
Native V27 tests must pass; the build/binary hash is checked, no Rust rebuild
occurs. Each backend additionally passes Python tests, known-optimum real
smokes and its own native deadline probe before hard cases.
