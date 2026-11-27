# Thread

**User:** I'm pasting one compact figure into a GitHub PR comment that reviewers often read on mobile
(450 px wide). Peak RSS memory across 4 compiler workloads (10 runs each) before and after our arena
allocator refactor is in `data/arena_memory.csv`.

**Assistant:** Columns: `workload`, `branch` (`main`, `arena_pr`), `run` (1–10), and `peak_rss_mb`.

**User:** Keep every label legible at 450 px width, include 10-run spread, and headline the biggest
memory savings (`type_check`).
