# figure-bench: arms compared

Neutral rows are measured the same way in every arm, on the Figure as saved (`neutral.py`).

## First submission

| Measure | v01_100_sonnet55_mintfig (mintfig) | v01_100_sonnet55_matplotlib_hook (matplotlib-hook) | v01_100_sonnet55_matplotlib_coached (matplotlib-coached) | v01_100_sonnet55_matplotlib_plain (matplotlib-plain) |
| :--- | ---: | ---: | ---: | ---: |
| Figure saved | 87/100 | 97/100 | 86/100 | 92/100 |
| No layout or text defect (all five below) | 87/100 | 57/100 | 46/100 | 31/100 |
| Smallest text >= 11 px at display width | 87/87 | 94/97 | 86/86 | 44/92 |
| No overlapping text | 87/87 | 86/97 | 71/86 | 86/92 |
| No text crossed by a line | 87/87 | 77/97 | 64/86 | 73/92 |
| No malformed text | 87/87 | 82/97 | 86/86 | 76/92 |
| No text past the canvas edge | 87/87 | 91/97 | 76/86 | 87/92 |
| Headline states a number | 87/87 | 81/97 | 86/86 | 79/92 |
| Headline number matches the answer key | 85/87 | 58/97 | 82/86 | 62/92 |
| Reply prose number matches the answer key | 93/100 | 84/100 | 67/100 | 63/100 |
| Uncertainty named (tasks with seeds, replicates or sampling) | 48/50 | 36/55 | 42/45 | 38/51 |
| Median smallest text (px) | 12.3 | 15.3 | 14.6 | 10.9 |
| Figures with a legend | 2 | 36 | 2 | 41 |

## Final submission

| Measure | v01_100_sonnet55_mintfig (mintfig) | v01_100_sonnet55_matplotlib_hook (matplotlib-hook) | v01_100_sonnet55_matplotlib_coached (matplotlib-coached) | v01_100_sonnet55_matplotlib_plain (matplotlib-plain) |
| :--- | ---: | ---: | ---: | ---: |
| Figure saved | 100/100 | 100/100 | 98/100 | 99/100 |
| No layout or text defect (all five below) | 100/100 | 91/100 | 54/100 | 35/100 |
| Smallest text >= 11 px at display width | 100/100 | 100/100 | 98/98 | 49/99 |
| No overlapping text | 100/100 | 99/100 | 81/98 | 93/99 |
| No text crossed by a line | 100/100 | 95/100 | 74/98 | 80/99 |
| No malformed text | 100/100 | 99/100 | 98/98 | 81/99 |
| No text past the canvas edge | 100/100 | 98/100 | 86/98 | 94/99 |
| Headline states a number | 100/100 | 95/100 | 98/98 | 84/99 |
| Headline number matches the answer key | 97/100 | 73/100 | 93/98 | 64/99 |
| Reply prose number matches the answer key | 94/100 | 84/100 | 68/100 | 63/100 |
| Uncertainty named (tasks with seeds, replicates or sampling) | 55/57 | 39/57 | 52/55 | 43/56 |
| Median smallest text (px) | 12.3 | 15.3 | 14.6 | 10.9 |
| Figures with a legend | 2 | 37 | 2 | 44 |

## Gate and time (each arm's own gate)

| Measure | v01_100_sonnet55_mintfig (mintfig) | v01_100_sonnet55_matplotlib_hook (matplotlib-hook) | v01_100_sonnet55_matplotlib_coached (matplotlib-coached) | v01_100_sonnet55_matplotlib_plain (matplotlib-plain) |
| :--- | ---: | ---: | ---: | ---: |
| Passed the arm's gate | 98/100 | 91/100 | 56/100 | 35/100 |
| Passed on the first submission | 75/100 | 57/100 | 48/100 | 31/100 |
| Median seconds to pass | 11.6 | 13.0 | 12.9 | 10.3 |
| Mean seconds to pass | 13.1 | 14.1 | 13.7 | 10.9 |
| p90 seconds to pass | 19.6 | 21.1 | 19.2 | 14.9 |
| Total seconds to pass | 1281.3 | 1285.3 | 765.5 | 381.4 |
| Median total seconds (all tasks) | 11.7 | 13.9 | 12.9 | 10.9 |
| Reply delivers the figure | 100 | 100 | 100 | 100 |
| Median seconds to first submit | 10.63 | 11.08 | 12.51 | 10.54 |
| Median agent think time (s) | 10.53 | 13.19 | 12.19 | 10.44 |
| Median render + audit time (s) | 0.631 | 0.611 | 0.604 | 0.457 |
