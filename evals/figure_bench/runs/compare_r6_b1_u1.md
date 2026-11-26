# figure-bench: arms compared

Neutral rows are measured the same way in every arm, on the Figure as saved (`neutral.py`).

## First submission

| Measure | r6 (mintfig) | b1 (matplotlib) | u1 (matplotlib-plain) |
| :--- | ---: | ---: | ---: |
| Figure saved | 14/15 | 15/15 | 14/15 |
| No layout or text defect (all five below) | 14/15 | 12/15 | 2/15 |
| Smallest text >= 11 px at display width | 14/14 | 15/15 | 6/14 |
| No overlapping text | 14/14 | 14/15 | 12/14 |
| No text crossed by a line | 14/14 | 15/15 | 7/14 |
| No malformed text | 14/14 | 15/15 | 12/14 |
| No text past the canvas edge | 14/14 | 13/15 | 13/14 |
| Headline states a number | 14/14 | 9/15 | 6/14 |
| Headline number matches the answer key | 13/14 | 4/15 | 4/14 |
| Reply prose number matches the answer key | 14/15 | 15/15 | 14/15 |
| Uncertainty named (tasks with seeds, replicates or sampling) | 3/3 | 3/4 | 2/3 |
| Median smallest text (px) | 12.3 | 15.3 | 10.9 |
| Figures with a legend | 0 | 6 | 7 |

## Final submission

| Measure | r6 (mintfig) | b1 (matplotlib) | u1 (matplotlib-plain) |
| :--- | ---: | ---: | ---: |
| Figure saved | 15/15 | 15/15 | 15/15 |
| No layout or text defect (all five below) | 15/15 | 15/15 | 2/15 |
| Smallest text >= 11 px at display width | 15/15 | 15/15 | 6/15 |
| No overlapping text | 15/15 | 15/15 | 13/15 |
| No text crossed by a line | 15/15 | 15/15 | 7/15 |
| No malformed text | 15/15 | 15/15 | 12/15 |
| No text past the canvas edge | 15/15 | 15/15 | 14/15 |
| Headline states a number | 15/15 | 9/15 | 7/15 |
| Headline number matches the answer key | 15/15 | 4/15 | 4/15 |
| Reply prose number matches the answer key | 14/15 | 15/15 | 14/15 |
| Uncertainty named (tasks with seeds, replicates or sampling) | 4/4 | 3/4 | 3/4 |
| Median smallest text (px) | 12.3 | 15.3 | 10.9 |
| Figures with a legend | 0 | 6 | 7 |

## Blind readers (the figure alone, final submission)

| Measure | r6 (mintfig) | b1 (matplotlib) | u1 (matplotlib-plain) |
| :--- | ---: | ---: | ---: |
| Reader answers the task's question correctly | 15/15 | 14/15 | 14/15 |
| Reader says the answer is not shown | 0/15 | 0/15 | 0/15 |

## Gate and time (each arm's own gate)

| Measure | r6 (mintfig) | b1 (matplotlib) | u1 (matplotlib-plain) |
| :--- | ---: | ---: | ---: |
| Passed the arm's gate | 14/15 | 15/15 | 2/15 |
| Passed on the first submission | 11/15 | 12/15 | 2/15 |
| Median seconds to pass | 16.6 | 19.5 | 14.8 |
| Reply delivers the figure | 15 | 15 | 15 |

## Notes

- Arms: `r6` mintfig (SKILL.md, `mint.explain`); `b1` plain Matplotlib, told the 700 px
  display width and the five defect checks, with feedback; `u1` plain Matplotlib, told
  neither and given no defect feedback (submit only says whether the figure saved).
  Same 15 tasks, one fresh Sonnet 5.5 agent per task and arm, 2026-11-25.
- Blind readers: 9 fresh Sonnet 5.5 agents, each shown 5 figures from 5 different tasks
  (PNG text chunks stripped, arm not named) and one question per task. The reader of
  batch_04 swapped two folder ids (u1/07 and b1/08, both Matplotlib arms); each answer
  is right for the other figure, so the corrected score is 15/15 in all three arms.
  Readers saw each PNG at full resolution, not at the 700 px display width.
- Wave 1 prompts (tasks 01–05) did not warn about macOS `sed -i`; three agents (two
  mintfig, one Matplotlib) lost an attempt to a silent failed edit. Waves 2–3 did.
- The neutral audit's ASCII-hyphen check is typographic ("-18%" for "−18%"); it is the
  weakest of the five and flags 2 of the uninstructed arm's 13 defective figures.
