# Thread

**User:** Someone pushed `broken_plot.py` (reading `data/release_scores.csv`) to our release review.
It has a truncated bar y-axis, rainbow colors, tiny unreadable labels, a `%%` typo, AND a wrong
headline number (+14%?!).

**Assistant:** I'll inspect `data/release_scores.csv` and `broken_plot.py`, recompute the true gain from
the CSV, and produce a clean repaired figure with an honest scale, colorblind-safe palette, and named
seed uncertainty.

**User:** Perfect — save the repaired figure as `figure.png`.
