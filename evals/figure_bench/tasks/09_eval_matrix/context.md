# Thread

**User:** Multilingual eval results for the new checkpoint are in
`data/eval_accuracy.csv`. Six languages by five task types. The previous
checkpoint's scores on the same grid are in `data/eval_accuracy_previous.csv`.

**Assistant:** Both files have `language`, `task` (QA, summarise, translate,
code, math) and `accuracy_pct`, one score per cell, 30 cells each, no gaps.

**User:** Last time Swahili was the blocker for announcing multilingual
support. Did the new checkpoint close that gap, and where is the model still
weakest? Leadership will ask whether it's a language problem, a task problem,
or one bad combination.

**Assistant:** I'll compare the two checkpoints where it matters and show where
the new one is still weakest.

**User:** Great — one figure for the launch-readiness thread.
