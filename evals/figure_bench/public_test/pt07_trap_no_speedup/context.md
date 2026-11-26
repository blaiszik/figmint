# Thread

**User:** We benchmarked our rewritten linear solver (`solver_v2`) against the
production implementation (`solver_v1`) over 10 independent trials each.
Timings are in `data/solver_trials.csv`.

**Assistant:** Columns: `solver` (`solver_v1`, `solver_v2`), `trial` (1–10),
and `runtime_ms`. 20 rows total, no missing values.

**User:** `solver_v2` came out with a lower average runtime! Can you put
together one figure for the performance PR comment summarizing the benchmark
results and whether we achieved a real speedup?

**Assistant:** Got it — comparing `solver_v2` against `solver_v1` across the
10 benchmark trials in `data/solver_trials.csv`.

**User:** One clean figure for the PR thread please.
