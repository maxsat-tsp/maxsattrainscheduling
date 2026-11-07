# V23: validation stopped, no hard-case screening

77 Rust and 107 Python tests passed. The finite-step smoke proved cost 11
in 27.7777 seconds; the rounded smoke was a valid native timeout at 30 s.
Both raw results were independently checked locally. The controller stopped
before the 13 unresolved cases. Preserve this as stopped validation, not 0/13.
