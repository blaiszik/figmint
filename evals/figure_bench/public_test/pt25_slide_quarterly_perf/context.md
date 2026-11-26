# Thread

**User:** I'm putting together a widescreen slide (1280 px wide) for the
quarterly engineering review. Regional p95 latency and throughput across
Q1–Q4 are in `data/quarterly_regions.csv`.

**Assistant:** Columns: `quarter` (Q1–Q4), `region` (`north-america`,
`europe`, `asia-pacific`, `south-america`), `p95_latency_ms`, `p95_sd_ms`,
`throughput_krps`, and `throughput_sd_krps`.

**User:** We rolled out regional edge caching in `asia-pacific` at the end
of Q2. Show both latency and throughput across all four regions so the
room can see the impact from the back row.

**Assistant:** I'll design a clean 1280 px slide figure pairing regional
p95 latency and throughput with quarterly s.d. uncertainty bands/bars.

**User:** One widescreen figure ready to drop directly onto a slide, please.
