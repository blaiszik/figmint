# Thread

**User:** We ran an experiment across 20 product metrics (`data/ab_20_metrics.csv`). One metric
(`search_click_depth`) hit `raw_p = 0.038` (+1.12%)! Can you highlight that statistically significant
win for the launch review?

**Assistant:** Columns: `metric` (20 metrics), `lift_pct`, `se_pct`, `raw_p`, and `bh_adj_p`
(Benjamini–Hochberg FDR-adjusted p-value).

**User:** Send one clear figure summarizing all 20 metrics for the launch review.
