# Thread

**User:** In `data/prior_figure.png`, we averaged all 6 pretraining runs together (`data/training_runs.csv`)
and it looked like loss just stalled around step 40k.

**Assistant:** Columns: `run_id` (R1–R6), `precision` (`BF16` vs `FP8`, 3 runs each), `step` (0–80k), `val_loss`.

**User:** Oh! Half of those runs used FP8! Please revise the figure to split by `precision` (showing the 3
runs/spread per group) and call out where FP8 diverges from BF16.
