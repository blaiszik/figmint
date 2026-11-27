# Contributing to `figure-bench` v0.1 (Work in Progress)

`figure-bench` is an open, library-agnostic benchmark for evaluating whether AI agents and
plotting libraries produce **legible, truthful, uncertainty-aware figures** at real reading
widths (`700 px` chat/dark, `450 px` phone/IDE, `1280 px` slide, and 72-column terminal).

You can contribute in under 5 minutes in any of three ways:

1. **Compete on the Open Leaderboard** with your favorite model, library, skill, or verifier hook.
2. **Submit a Real-World Failure Task** where agents or libraries routinely mislead readers.
3. **Improve `mintfig` (or your own skill/hook)** via the Skill/Library Arena.

---

## 1. Compete on the Open Leaderboard (5 Minutes)

You do **not** need to use `mintfig` to compete. Any tool that writes `figure.png` (plus an
optional `figure.svg` for vector-text auditing) and `reply.md` is a first-class citizen:
`matplotlib`, `seaborn`, `altair`, `plotly`, `plotnine`, `ggplot2`, `d3`, `vega-lite`,
`mintfig`, or your own custom skill/prompt.

### Step 1: Produce task outputs

Organize your outputs by task ID for the split you are evaluating (`dev`, `public-test`, or `heldout`):

```text
my_outputs/
  pt01_volcano_omics/
    figure.png        # required (except surface="terminal" tasks)
    figure.svg        # optional — enables vector font-size & overlap audit for non-Matplotlib stacks!
    reply.md          # required — the chat reply you would send the user (<= 60 prose words)
  pt02_raman_peaks/
    figure.png
    reply.md
  ...
```

### Step 2: Grade locally with `grade-dir`

```bash
python evals/figure_bench/bench.py grade-dir my_outputs/ \
    --split public-test \
    --out evals/figure_bench/leaderboard/submissions/<your_submission_id>.json \
    --markdown my_outputs/report.md
```

Fill in the submission metadata fields defined in `evals/figure_bench/leaderboard/schema.json`
(`submission_id`, `date`, `team`, `model`, `library`, `skill_or_prompt`, `hook_enabled`,
`provenance`).

### Step 3: Verify & rebuild the leaderboard site

```bash
python evals/figure_bench/leaderboard/verify_submission.py \
    evals/figure_bench/leaderboard/submissions/<your_submission_id>.json

python evals/figure_bench/leaderboard/build_site.py
```

`verify_submission.py` validates every schema field, checks required provenance, confirms
aggregate scores match the exact `per_task` averages (preventing tampered totals), and
re-checks PNG dimensions whenever `artifacts_dir` is bundled.

### Step 4: Open a Pull Request

Open a PR adding your JSON under `evals/figure_bench/leaderboard/submissions/`. GitHub
Actions (`.github/workflows/figure-bench-verify.yml`) automatically runs `verify_submission.py`
and `build_site.py` on your PR.

---

## 2. Submit a Real-World Failure Task (`new-task`)

Have a real dataset or scientific/engineering thread where agents routinely ship a truncated
axis, hide seed variance, overclaim noise, or produce illegible labels? Turn it into a task!

### Step 1: Scaffold the task folder

```bash
python evals/figure_bench/bench.py new-task \
    --id pt51_your_task_slug \
    --split public-test \
    --track epistemic_traps \
    --domain Systems
```

Valid splits: `dev` (`tasks/`), `public-test` (`public_test/`), `heldout` (`heldout/`).  
Valid tracks: `science_uncertainty`, `swe_coding`, `epistemic_traps`, `multiturn_edit`,
`multi_surface`, `byo_repair`.

### Step 2: Add compact deterministic data & realistic context

- Keep `data/` files compact (< 50 KB) and deterministically reproducible (synthetic or
  permissively licensed public data — never proprietary or private data).
- Write `context.md` (12–25 lines) as a natural conversation between a user and an assistant.
  **Never mention `mintfig` or any specific plotting library in `context.md`.**
- Populate `rubric.json` (`schema_version: "0.1"`) with exact `accept` values computed
  directly from `data/`, realistic tolerances (`rel_tol` / `abs_tol`), uncertainty/no-effect
  flags, and three blind-reader questions (`primary`, `uncertainty`, `nuance`).

### Step 3: Validate before opening a PR

```bash
python evals/figure_bench/bench.py validate-tasks
```

CI automatically runs `validate-tasks` on every PR touching `tasks/`, `public_test/`, or `heldout/`.

---

## 3. Improve `mintfig` (or Your Skill/Hook) in the Skill/Library Arena

Want to test whether a new `SKILL.md` rule, a `mint.check` verifier hook, or a custom prompt
improves real agent figure quality?

1. **Iterate only on `dev` (`tasks/`)** — never tune prompts, skills, or library heuristics
   against `heldout/`.
2. Compare arms head-to-head on identical tasks and models:
   - `--arm mintfig` (`SKILL.md` + `mint.explain`)
   - `--arm matplotlib-hook` (plain Matplotlib + `mint.check` feedback loop)
   - `--arm matplotlib-coached` (prompt-coached plain Matplotlib, no `mintfig`, no hook)
   - `--arm matplotlib` (told display width & defect rules)
   - `--arm matplotlib-plain` (uncoached baseline, display width & surface only)
   - `--arm custom --skill path/to/SKILL.md --library seaborn`
3. Run a blinded human reading check at true display width (`700 px` or `450 px`) using
   `evals/figure_bench/human_study/index.html` so improvements are verified by human eyes,
   not just automated metrics.
4. Report both first-submission and final-submission numbers honestly in your PR description!
