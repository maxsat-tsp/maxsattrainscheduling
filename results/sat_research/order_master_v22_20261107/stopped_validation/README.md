# V22 stopped at known-cost validation

76 Rust and 106 Python tests passed. origA1/finsteps123 proved cost=LB=UB=11
in 18.7200 seconds. origA1/infsteps180 was a valid native timeout at 30 seconds.
The controller correctly stopped before measuring any of the 13 hard cases.
These are two validation records, not a 0/13 performance trial. Independent
local audit passes for both raw records; validation_passed=false is preserved.
