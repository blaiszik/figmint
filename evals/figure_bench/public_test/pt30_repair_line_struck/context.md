# Thread

**User:** Our load-scaling script (`data/broken_plot.py`) on
`data/throughput.csv` rendered with several visual glitches: lines slice
right through the annotations, negative deltas use raw ASCII hyphens,
there is a `%%` typo in the title/label, and the right-hand label clips
off the edge of the image.

**Assistant:** I see `data/throughput.csv` (`concurrency`, `release`,
`req_per_sec`, `delta_vs_v1_pct`) across releases `v1.0`, `v1.1`, and
`v2.0` from concurrency 1 to 128, along with `data/broken_plot.py`.

**User:** Clean up the plot completely so labels sit cleanly off the
lines, formatting is crisp (proper minus signs, no `%%`), and nothing
clips at the canvas edge.

**Assistant:** I'll rebuild the scaling figure cleanly with unobstructed
labels, accurate deltas, and proper typography at 700 px width.

**User:** One clean figure for the release notes, please.
