# Thread

**User:** I just got paged while away from my laptop and I'm reading this
on my phone (450 px wide screen). Per-minute regional error rates from
18:00–18:35 UTC are in `data/incident_5m.csv`. Alert threshold is 1.0%.

**Assistant:** Columns: `minute`, `timestamp`, `region` (`eu-west`,
`us-east`, `ap-south`), `error_rate_pct`, and `requests_per_min`.

**User:** Tell me fast: is this global or isolated to one region, how high
did the error rate spike, and did the 18:28 rollback bring it back down?

**Assistant:** I'll build a compact figure sized specifically for a 450 px
phone viewport so every label and line is immediately readable without
pinch-zooming.

**User:** Perfect — one phone-sized figure for the incident channel.
