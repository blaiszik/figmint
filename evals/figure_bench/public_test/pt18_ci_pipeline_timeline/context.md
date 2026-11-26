# Thread

**User:** Our main CI pipeline is taking 14 minutes even though we split
integration tests into four parallel shards. The workflow job/step timing
export is in `data/ci_run.json`.

**Assistant:** `ci_run.json` contains 8 jobs with `started_at`,
`completed_at`, `duration_s`, `depends_on`, and per-step timings across
the 840 s (14.0 min) run.

**User:** Show the team where the critical path actually sits and which
job is blocking `package-artifacts` from starting sooner.

**Assistant:** I'll plot the parallel job timeline across the 14-minute
build, highlight the critical-path bottleneck, and call out how long the
other shards sit idle waiting on it.

**User:** One figure for our build-speed engineering thread, please.
