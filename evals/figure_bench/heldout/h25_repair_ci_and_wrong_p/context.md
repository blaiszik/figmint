# Thread

**User:** Someone submitted `broken_plot.py` (`data/experiment_scores.csv`, 8 runs per arm) claiming
`variant_x significantly outperforms control by +12.5% (95% CI)` — even though the script actually
plotted ±1 SEM, truncated the y-axis at 58, and got the percentage wrong!

**Assistant:** I'll recompute the true means and 95% CIs from `data/experiment_scores.csv` and repair
the script with an honest scale, proper 95% CI (plus individual points), and an accurate conclusion.

**User:** Thanks — save the repaired figure to `figure.png`.
