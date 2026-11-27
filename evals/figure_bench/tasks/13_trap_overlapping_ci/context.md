# Thread

**User:** We finished our five-seed benchmark sweep for three new reranking
candidates against `baseline`. Results are in `data/seed_eval.csv`.

**Assistant:** Thanks. I see columns `variant` (`baseline`, `cand_a`, `cand_b`,
`cand_c`), `seed` (0–4), and `f1_score` (macro F1, %). 20 rows, no missing
values.

**User:** Looking at the averages, `cand_b` is ahead of `baseline`! The release
lead wants one figure for the release review channel showing how the candidates
compare and whether we are ready to ship `cand_b` this week.

**Assistant:** Got it — evaluating all four variants across the five seeds from
`data/seed_eval.csv`.

**User:** Right, one clean figure I can paste straight into the release chat.
