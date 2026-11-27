# Thread

**User:** Someone sent me `data/broken_plot.py` to visualize our 5-class
support-ticket confusion matrix (`data/confusion.csv`, 1,000 tickets).
It looks unreadable in chat and the headline accuracy doesn't match my
eval logs.

**Assistant:** I checked `data/confusion.csv` and `data/broken_plot.py`.
The script uses the `jet` rainbow colormap, renders tiny 8 pt labels on a
13×9 canvas, overlaps count and percentage strings inside every cell, and
claims 96.4% accuracy when the diagonal sum is much lower.

**User:** Please replace the broken chart with a clean, perceptually
uniform heatmap whose headline gives the true accuracy and highlights the
main misrouting error.

**Assistant:** I'll recompute overall accuracy and per-class errors from
`data/confusion.csv` and render a clean 700 px figure.

**User:** One repaired figure for the classifier review thread, please.
