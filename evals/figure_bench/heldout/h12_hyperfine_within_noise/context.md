# Thread

**User:** I tried replacing our hash-table probing loop with an SIMD
candidate and benchmarked both binaries with `hyperfine --export-json`
(25 runs each). Files are `data/baseline_bench.json` and
`data/candidate_bench.json`.

**Assistant:** Both files contain a single `hyperfine` result with 25
per-run timings in seconds, `mean`, `stddev`, and `median`.

**User:** The candidate's mean came out slightly lower. Can I put in the
PR description that the SIMD rewrite speeds up indexing, or is this just
measurement noise?

**Assistant:** I'll compare the full run distributions and ±1 s.d.
intervals for baseline and candidate and tell you honestly whether the
difference clears noise.

**User:** One figure I can link in the PR to settle the question, please.
