# Leaderboard Submissions (`figure-bench v0.1`)

Each `.json` file in this directory is a verified submission to the open **figure-bench v0.1** leaderboard.

## Initial Seed Submissions (`v0.1-initial-15`)

The three initial seed files import the real measured 15-task baseline comparison from
`evals/figure_bench/runs/compare_r6_b1_u1.md` (2026-11-25, Claude Sonnet 5.5):

- `v01_seed_r6_mintfig_sonnet55.json` — `mintfig` (`SKILL.md` + `mint.explain`)
- `v01_seed_b1_matplotlib_told_sonnet55.json` — `matplotlib` (`matplotlib` arm: told 700 px width & 5 defect checks, with submit feedback)
- `v01_seed_u1_matplotlib_plain_sonnet55.json` — `matplotlib` (`matplotlib-plain` arm: untaught baseline, no defect feedback)

These seeds are explicitly tagged `split: "v0.1-initial-15"` and `work_in_progress: true`
because they cover the original 15 tasks (10 `dev` + 5 `heldout`) rather than the full
60-task v0.1 suite.

## Submitting Your Own Run

1. Run any model, plotting library (`matplotlib`, `seaborn`, `altair`, `plotly`, `plotnine`,
   `ggplot2`, `d3`, `mintfig`, or custom skills/hooks) on `dev` or `public-test`.
2. Grade your output directory with `python evals/figure_bench/bench.py grade-dir ...`.
3. Add your submission JSON file here following `../schema.json`.
4. Verify locally before opening a PR:

```bash
python evals/figure_bench/leaderboard/verify_submission.py evals/figure_bench/leaderboard/submissions/<your_file>.json
python evals/figure_bench/leaderboard/build_site.py
```

Pull requests touching `evals/figure_bench/leaderboard/submissions/**` automatically run
`verify_submission.py` in CI via `.github/workflows/figure-bench-verify.yml`.
