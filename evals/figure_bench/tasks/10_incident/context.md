# Thread

**User:** We had a pager storm in mid-November. Daily error rates for five
services, 1–21 Nov, are in `data/error_rates.csv`.

**Assistant:** Columns: `date` (ISO), `service` (auth, search, payments,
uploads, notifications), `error_rate` (fraction of requests that failed).
Normal rates differ a lot between services, from about 1e-5 to 1e-3, so a log
scale will be needed.

**User:** For the postmortem I need to show which service actually spiked, on
which day, and how far above its normal rate it went. The others should be
visible as context so nobody can say we hid a second problem.

**Assistant:** I'll plot all five over time on a log axis, highlight the one
that spiked, and give its peak relative to its usual level.

**User:** One figure please, for the postmortem doc.
