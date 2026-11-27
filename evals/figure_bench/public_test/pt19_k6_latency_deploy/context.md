# Thread

**User:** Load-test latency metrics around today's 14:30 UTC deployment
(`deploy_v4.12.0`) are in `data/latency_timeseries.csv`. Our p99 latency
SLA is 500 ms.

**Assistant:** The CSV has 60 one-minute buckets (`minute`, `timestamp`,
`p50_ms`, `p95_ms`, `p99_ms`, `rps`, `deploy_event`), with
`deploy_v4.12.0` marked at minute 30.

**User:** The release owner says median latency looks fine so the deploy
is harmless. Show what actually happened to tail latency versus the
500 ms SLA.

**Assistant:** I'll plot p50, p95, and p99 over the 60-minute window with
the deploy timestamp and 500 ms SLA line marked.

**User:** One figure I can drop into the rollback decision thread, please.
