# V26 native checks and independently audited original smokes

78 native Rust and 111 Python tests pass; their log hashes match the original
build manifest. The two proved smokes match known costs/bounds. Continuous
smoke is a valid native timeout. A missing partial-SAT telemetry field stopped
the original validator, not the solver. Raw data and the original progress
before the validator fix are retained here. The revised validator assesses
these same JSON files without rerunning them. Native timeout telemetry is
explicitly missing rather than filled with zero. Screening is separate.

Test logs use lossless gzip; compare the SHA-256 of their decompressed bytes
with rust_tests_log_sha256 and python_tests_log_sha256 in build_manifest.json.
