# V24 validation stopped before the hard-case screen

The same V23 release binary used full assumptions. Independent checks accept
the two proved schedules and their costs/bounds. origA1/cont timed out at 30
seconds without an invalid solution. The all-objective validation gate failed,
so the 13-case screen and its followup never ran. This is not a 0/13 result.

Raw JSON, stdout, stderr, provenance, measurement receipts and validation
progress are preserved in raw_snapshot.tar.gz; independent_audit.json records
its SHA-256. Solver source is d8e2509, runner source is 080edb7. The source
build manifest records the frozen binary hash. Full-assumption telemetry is
checked in each record. No submission or full-coverage claim is made.
