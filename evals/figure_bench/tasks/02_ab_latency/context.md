# Thread

**User:** We ran the A/B test on the new checkout flow for a week. I exported
one row per session to `data/checkout_sessions.csv`.

**Assistant:** Columns: `arm` ("control" or "new flow"), `session`,
`latency_ms` (time from "Pay" click to confirmation). 400 sessions per arm.
Latencies are right-skewed with a long tail, so I'd compare medians rather
than means.

**User:** Makes sense. Product wants to know if the new flow is actually
faster for a typical user, and whether the slow tail got worse — we had
complaints about 2-second checkouts.

**Assistant:** I can show the full distribution of both arms so the tail is
visible, plus the median difference.

**User:** Please do — one figure for the product channel.
