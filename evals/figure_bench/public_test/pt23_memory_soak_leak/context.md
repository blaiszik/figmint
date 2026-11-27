# Thread

**User:** We ran a 48-hour staging soak test across our four background
workers before cutting the release. Hourly RSS memory readings are in
`data/rss_mb.csv`. Container OOM limit is 2,048 MB (2 GB).

**Assistant:** Columns: `hour` (0 to 48), `worker` (`worker-api`,
`worker-scheduler`, `worker-notifier`, `worker-ingest`), and `rss_mb`.

**User:** One worker looks suspicious in staging logs. Show all four
workers over the 48-hour soak, quantify the leak rate, and show how soon
it will hit the 2,048 MB OOM cap.

**Assistant:** I'll plot RSS over time for all four workers, fit the linear
growth rate on the leaking worker, and mark the 2,048 MB cap.

**User:** One figure for the release blocker ticket, please.
