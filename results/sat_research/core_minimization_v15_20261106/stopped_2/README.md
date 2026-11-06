# V15 stopped after two valid timeouts and a third failed attempt

The count-only core-reduction trial stopped at 15:07:29 UTC on 2026-11-06.
`trackA11/infsteps180` and `trackA12/infsteps180` completed validly without
proving optimality. Both were independently audited after download.
`stationA11/infsteps180` exceeded the external guard and exited 124; its
placeholder JSON and logs are preserved, but it is not an accepted result.
The remaining 12 cases were not attempted. This is not a 0/15 result.

The historical `core_minimization_audit.json` describes the two completed
cases, while systemd and the retained logs document the subsequent failure.
An extra core check had no native work limit and could consume the remaining
wall-clock budget inside MiniSAT. V16 adds an interruptible MiniSAT adapter
and a separate native conflict budget per core check. Inconclusive extra
checks preserve the previously proved core; they never create an UNSAT proof.

V15 is diagnostic evidence. Its two timeouts are not relabelled as results
for the new conflict-limited strategy, which is measured separately.

Archive SHA-256:
`7c93b3dbe79ca08867cdd005c96a11c2aaea98f8a54dd009124682d8e72bfa84`.
