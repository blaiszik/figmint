# figure-bench v0.1 (work in progress)

> **Status:** `figure-bench v0.1` is an active work in progress. The 60-task v0.1 suite,
> library-agnostic scoring engine, open leaderboard, and display-width-locked human reader
> study are live; initial leaderboard seed rows currently reflect our measured 15-task
> baseline (`v0.1-initial-15`) while full 60-task runs across models and plotting libraries
> are collected.

**Can an AI agent turn a real conversation and dataset into a legible, truthful,
uncertainty-aware figure — fast, and at the exact width a human will actually read it?**

`figure-bench` is an open, library-agnostic benchmark. Bring any model (`Claude`, `GPT`,
`Gemini`, open-weights) and any plotting stack (`matplotlib`, `seaborn`, `altair`, `plotly`,
`plotnine`, `ggplot2`, `d3`, `mintfig`, or your own skills and verifier hooks).

- **Visual Results & Matplotlib Failure Anatomy:** [`docs/figure-bench.md`](../../docs/figure-bench.md)
- **Open Leaderboard & Visual Explorer:** [`site/index.html`](site/index.html) (zero-CDN static page)
- **Human Blind Reader Study App:** [`human_study/index.html`](human_study/index.html) (exact `700 px` / `450 px` display-width lock)
- **5-Minute Contributor Guide:** [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## Benchmark Architecture: 60 Tasks · 3 Splits · 6 Tracks

Every task is a realistic conversation (`context.md`), compact deterministic dataset(s) in
`data/`, and a canonical `rubric.json` (`schema_version: "0.1"`). Prompts never mention
`mintfig` or any specific library.

### Splits

| Split | Directory | Tasks | Purpose |
| :--- | :--- | ---: | :--- |
| **`dev`** | `tasks/` | 15 | Open development & iteration (original 10 + 5 scientific/trap/edit tasks) |
| **`public-test`** | `public_test/` | 30 | Frozen public evaluation suite for open leaderboard comparisons |
| **`heldout`** | `heldout/` | 15 | Held-out generalization split (never used to tune `mintfig` or `SKILL.md`) |
| **Total** | | **60** | |

### Tracks

| Track | ID | Tasks | What It Evaluates |
| :--- | :--- | ---: | :--- |
| **Science & Uncertainty** | `science_uncertainty` | 19 | Multi-seed ablations, dose-response, meta-analysis forests, survival curves, volcano plots, Raman spectra, Arrhenius kinetics, RL seed bands, alloy replicates, ocean pH, enzyme kinetics, clinical funnels |
| **SWE & Quantitative Coding** | `swe_coding` | 13 | Latency tails, eval matrices, incidents, `hyperfine` & `pytest-benchmark` diffs, CI timelines, `k6` p99 deploy regressions, `esbuild` bundle waterfalls, LLM Pareto frontiers, signup funnels, soak memory leaks, Chrome traces |
| **Epistemic Traps & Refusals** | `epistemic_traps` | 12 | Overlapping CIs, no-effect traps (must not overclaim speedup/improvement), Simpson's paradox, `n=3` small samples, near-zero `%` traps, truncated-bar bait, missing controls, defective cells & contaminated plates |
| **Multi-Turn Figure Editing** | `multiturn_edit` | 6 | Targeted revisions to a prior figure: fixing definitions/units, switching baselines, linear-to-log conversion, adding hidden replicates, highlighting failing subsets |
| **Multi-Surface Delivery** | `multi_surface` | 5 | Legibility across `450 px` narrow phone/IDE sidebars, `1280 px` presentation slides, dark dashboard cards, and 72-column SSH terminal sessions |
| **BYO-Matplotlib Repair** | `byo_repair` | 5 | Repairing broken existing Matplotlib scripts with wrong headline numbers, `jet` colormaps, truncated bars, struck labels, and unlabelled CI bands |

---

## Library-Agnostic Scoring

Every submission — regardless of plotting library — is graded across four automated
dimensions plus optional blinded reader evaluation:

1. **Visual Quality (`visual_quality`, 0–100):**
   - For Matplotlib-backed runs, `neutral.py` hooks `Figure.savefig` without importing
     `mintfig` and checks text legibility (`>= 11 px` at target display width), text overlap,
     text crossed by lines, malformed text (`%%`, doubled words, ASCII hyphen minus,
     `nan`/`None`), and canvas-edge clipping.
   - For any non-Matplotlib stack (`altair`, `plotly`, `ggplot2`, `d3`, etc.), `svg_audit.py`
     audits exported `figure.svg` vector geometry and `pixel_audit.py` inspects `figure.png`
     for display-width scaling, rainbow/jet hue sweeps, CVD/grayscale luminance contrast, and
     blank/clipped canvases.
2. **Claim Accuracy (`claim_accuracy`, 0–100):** Whether the headline/takeaway (or reply prose)
   states the key quantitative finding within each task's `rel_tol`/`abs_tol`.
3. **Uncertainty Calibration (`uncertainty_calibration`, 0–100):** Whether uncertainty
   (CI, s.d., seeds, replicates, `n`) is named when required, AND on `no_effect_trap` tasks
   whether the figure avoids overclaiming noise (`"clearly beats"`, `"proves"`, `"significantly
   outperforms"`, etc.).
4. **Delivery (`delivery_rate`, 0–100):** Concise reply (`<= 60` prose words) delivering the
   figure image (or `<= 72`-col text block for `surface="terminal"`).
5. **Blind Reader Comprehension (`reader_score`, 0–100):** Blinded human or VLM readers viewing
   each PNG **locked to its exact display width (`700 px` or `450 px`)** answer three
   structured questions (`primary`, `uncertainty`, `nuance`) while timed with
   `performance.now()`.

---

## Initial Seed Results (`v0.1-initial-15`, Work in Progress)

![Progress across three fix cycles](progress.png)

Full comparison table and notes: [`runs/compare_r6_b1_u1.md`](runs/compare_r6_b1_u1.md).
These three initial leaderboard seeds (`split: "v0.1-initial-15"`) come from a real 15-task run
(10 `dev` + 5 `heldout`, one fresh Claude Sonnet 5.5 agent per task and arm, 2026-11-25):

| Submission (`v0.1-initial-15`) | Library | Hook | First-Submit Clean | Final Visual | Claim Accuracy | Uncertainty | Reader* | Delivery | Median Time | Composite |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `r6` (`mintfig`) | `mintfig` | ON | **93.3%** (14/15) | **100.0** | **100.0** | **100.0** (4/4) | 100.0 | 100.0 | 16.6 s | **100.0** |
| `b1` (`matplotlib`, told rules) | `matplotlib` | ON | 80.0% (12/15) | 100.0 | 26.7 | 75.0 (3/4) | 93.3 | 100.0 | 19.5 s | **68.4** |
| `u1` (`matplotlib-plain`, untaught) | `matplotlib` | OFF | **13.3%** (2/15) | **13.3** | 26.7 | 75.0 (3/4) | 93.3 | 100.0 | 14.8 s | **33.4** |

\* Blind VLM readers scored 15/15 (`r6`), 14/15 (`b1`), and 14/15 (`u1`) raw (one reader
swapped folder IDs `u1/07` and `b1/08`, making the corrected score 15/15 in all three arms).
Readers in that early run viewed full-resolution PNGs rather than display-width-locked images.

### What this does and does not show

- **Without guardrails**, a strong model writing plain Matplotlib shipped a layout or text
  defect on 13 of 15 figures (`text < 11 px` at `700 px`, labels crossed by lines, overlapping
  text). Told the constraints with feedback (`b1`), it fixed layout defects by the final
  attempt — `mintfig` (`r6`) avoided them upfront (14/15 clean on the first try).
- **Message-first headlines:** `mintfig` stated the verified quantitative answer in the figure
  headline on 15/15 tasks vs 4/15 for both Matplotlib arms.
- **What we still need to measure:** Full 60-task runs across multiple models, plotting
  libraries (`seaborn`, `altair`, `plotly`, `ggplot2`, `matplotlib-hook`), and **display-width-locked
  human blind reader studies** via [`human_study/index.html`](human_study/index.html).

---

## Quick Start: Run, Grade & Compete

### 1. List and validate tasks

```bash
python evals/figure_bench/bench.py list --split public-test
python evals/figure_bench/bench.py validate-tasks
```

### 2. Grade any output directory (Bring Your Own Library/Model)

```bash
python evals/figure_bench/bench.py grade-dir my_outputs/ \
    --split public-test \
    --out evals/figure_bench/leaderboard/submissions/my_run.json
```

### 3. Run built-in agent arms (`mintfig`, `matplotlib`, `matplotlib-hook`, `matplotlib-plain`, `custom`)

```bash
python evals/figure_bench/bench.py start 01_ablation --run runs/exp1 --arm mintfig
python evals/figure_bench/bench.py submit 01_ablation --run runs/exp1 runs/exp1/01_ablation/figure.py \
    --reply runs/exp1/01_ablation/reply.md
python evals/figure_bench/bench.py grade --run runs/exp1
python evals/figure_bench/bench.py compare runs/r6 runs/b1 runs/u1
```

### 4. Verify a leaderboard submission & rebuild the static site

```bash
python evals/figure_bench/leaderboard/verify_submission.py evals/figure_bench/leaderboard/submissions
python evals/figure_bench/leaderboard/build_site.py
```

### 5. Run a display-width-locked human blind reader study

```bash
python evals/figure_bench/bench.py readers-prepare runs/r6 runs/b1 --out readers/study01 --display-width 700
# Open evals/figure_bench/human_study/index.html in any browser (zero-CDN, works over file://)
python evals/figure_bench/bench.py readers-score readers/study01
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the 5-minute guide to submitting leaderboard
entries, real-world failure tasks (`bench.py new-task`), and skill/library improvements.
