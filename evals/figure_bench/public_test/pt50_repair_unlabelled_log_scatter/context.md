# Thread

**User:** `broken_plot.py` (`data/parser_scaling.csv`) plots 4 orders of magnitude of JSON payload sizes
(3 KB to 30 MB) on linear axes — crushing 80% of the points into the bottom-left corner — uses a `jet`
colormap, omits both axis labels, and claims `R² = 0.98`!

**Assistant:** I'll recompute the true log–log scaling slope and R² from `data/parser_scaling.csv` and
produce a clean log–log scatter with labelled axes and a fit line.

**User:** Great — save the repaired figure to `figure.png`.
