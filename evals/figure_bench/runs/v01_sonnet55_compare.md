# figure-bench: arms compared

Neutral rows are measured the same way in every arm, on the Figure as saved (`neutral.py`).

## First submission

| Measure | v01_sonnet55_mintfig (mintfig) | v01_sonnet55_matplotlib_plain (matplotlib-plain) | v01_sonnet55_matplotlib_hook (matplotlib-hook) |
| :--- | ---: | ---: | ---: |
| Figure saved | 35/60 | 23/60 | 31/60 |
| No layout or text defect (all five below) | 35/60 | 9/60 | 15/60 |
| Smallest text >= 11 px at display width | 35/35 | 13/23 | 31/31 |
| No overlapping text | 35/35 | 21/23 | 25/31 |
| No text crossed by a line | 35/35 | 18/23 | 22/31 |
| No malformed text | 35/35 | 17/23 | 24/31 |
| No text past the canvas edge | 35/35 | 22/23 | 30/31 |
| Headline states a number | 35/35 | 17/23 | 21/31 |
| Headline number matches the answer key | 33/35 | 11/23 | 13/31 |
| Reply prose number matches the answer key | 53/60 | 39/60 | 48/60 |
| Uncertainty named (tasks with seeds, replicates or sampling) | 19/22 | 8/11 | 10/18 |
| Median smallest text (px) | 12.3 | 12.2 | 15.3 |
| Figures with a legend | 3 | 11 | 13 |

## Final submission

| Measure | v01_sonnet55_mintfig (mintfig) | v01_sonnet55_matplotlib_plain (matplotlib-plain) | v01_sonnet55_matplotlib_hook (matplotlib-hook) |
| :--- | ---: | ---: | ---: |
| Figure saved | 57/60 | 60/60 | 57/60 |
| No layout or text defect (all five below) | 57/60 | 21/60 | 48/60 |
| Smallest text >= 11 px at display width | 57/57 | 28/60 | 56/57 |
| No overlapping text | 57/57 | 55/60 | 55/57 |
| No text crossed by a line | 57/57 | 49/60 | 52/57 |
| No malformed text | 57/57 | 49/60 | 57/57 |
| No text past the canvas edge | 57/57 | 57/60 | 55/57 |
| Headline states a number | 57/57 | 49/60 | 50/57 |
| Headline number matches the answer key | 53/57 | 36/60 | 39/57 |
| Reply prose number matches the answer key | 53/60 | 39/60 | 47/60 |
| Uncertainty named (tasks with seeds, replicates or sampling) | 29/33 | 24/33 | 20/31 |
| Median smallest text (px) | 12.3 | 10.9 | 15.3 |
| Figures with a legend | 3 | 26 | 22 |

## Gate and time (each arm's own gate)

| Measure | v01_sonnet55_mintfig (mintfig) | v01_sonnet55_matplotlib_plain (matplotlib-plain) | v01_sonnet55_matplotlib_hook (matplotlib-hook) |
| :--- | ---: | ---: | ---: |
| Passed the arm's gate | 56/60 | 21/60 | 48/60 |
| Passed on the first submission | 33/60 | 9/60 | 15/60 |
| Median seconds to pass | 13.2 | 14.0 | 16.6 |
| Reply delivers the figure | 57 | 60 | 60 |
