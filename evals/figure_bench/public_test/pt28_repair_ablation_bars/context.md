# Thread

**User:** I drafted a quick Matplotlib script (`data/broken_plot.py`) for
our retrieval ablation results (`data/ablation.csv`, 5 variants × 6 seeds),
but reviewers flagged multiple problems with both the headline claim and
how the chart renders in a 700 px chat column.

**Assistant:** I see `data/ablation.csv` (`variant`, `seed`, `f1_score`)
and `data/broken_plot.py`. The draft script truncates the bar y-axis to
0.65–0.85, draws unlabelled error bars on a 14×5 canvas that shrinks text
under 8 px at 700 px width, and states a wrong headline gain.

**User:** Please fix the plot cleanly: verify every number directly from
`data/ablation.csv`, make the baseline honest, label what the error bars
represent, and size it cleanly for 700 px chat viewing.

**Assistant:** I'll audit the data, repair all four issues, and produce a
clean, accurate figure.

**User:** One repaired figure for the experiment thread, please.
