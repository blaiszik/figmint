# Thread

**User:** A teammate sent `data/broken_plot.py` plotting our regional API
latency samples (`data/latencies.csv`, 60 requests per region), but the
headline median looks way too high, the y-axis has no label or units, and
the text is tiny when pasted into a 700 px chat window.

**Assistant:** I checked `data/latencies.csv` (`region`, `request_id`,
`latency_ms`) and `data/broken_plot.py`. The draft uses a 14×5 canvas with
9 pt ticks, omits the y-axis label, and claims a 312 ms median for
`ap-northeast` that doesn't match the data.

**User:** Please fix the plot cleanly so the headline states the true
`ap-northeast` median (and how it compares to `us-east`), the axis is
labelled with units, and all text is legible at 700 px.

**Assistant:** I'll recompute the regional medians and spreads from
`data/latencies.csv` and produce a clean, readable figure.

**User:** One repaired figure for the latency review thread, please.
