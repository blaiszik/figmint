# Thread

**User:** We measured stop-the-world GC pause percentiles from p50 to p99.9 across 50,000 cycles for
`Go-1.23`, `JVM-G1GC`, and `JVM-ZGC` (`data/gc_pause_percentiles.csv`).

**Assistant:** Columns: `runtime`, `percentile` (50 to 99.9), and `pause_ms`.

**User:** Plot the tail pause profile (log scale on pause time) so the runtime team can see how
`JVM-G1GC` blows up at p99.9 compared to `JVM-ZGC` and `Go-1.23`.
