# Thread

**User:** CI flagged a potential performance regression on my query-filter
PR. The `pytest-benchmark` exports for `main` and the PR are in
`data/base.json` and `data/pr.json`.

**Assistant:** Both files contain 6 API endpoint benchmarks (`rounds: 40`
each) with `mean`, `stddev`, `median`, `iqr`, and raw timings in seconds.

**User:** I need to see which endpoint actually regressed, by how much in
mean latency, and whether the other five endpoints are just noise.

**Assistant:** I'll compare all six endpoints between `base` and `pr`
with their run-to-run spread and highlight the regressed endpoint.

**User:** One clear figure for the PR review comment, please.
