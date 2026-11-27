# figure-bench v0.1 (work in progress)

> **Status:** `figure-bench v0.1` includes **100 deterministic tasks** (`25 dev` /
> `50 public-test` / `25 heldout` across 6 tracks and 6 surfaces), hardened library-agnostic
> scoring with structural invariants (`forbid_truncated_bars`, `require_log_scale`, `min_panels`),
> full per-task/per-attempt timing capture, an external benchmark bridge
> ([`EXTERNAL_BENCHMARKS.md`](EXTERNAL_BENCHMARKS.md)), verified **full 100-task × 3-arm**
> Claude Sonnet 5.5 leaderboard entries, and a display-width-locked human reader study app.
> Community runs across additional models and plotting libraries are welcome via PR.

**Can an AI agent turn a real conversation and dataset into a legible, truthful,
uncertainty-aware figure — fast, and at the exact width a human will actually read it?**

`figure-bench` is an open, library-agnostic benchmark. Bring any model (`Claude`, `GPT`,
`Gemini`, open-weights) and any plotting stack (`matplotlib`, `seaborn`, `altair`, `plotly`,
`plotnine`, `ggplot2`, `d3`, `mintfig`, or your own skills and verifier hooks).

- **Visual Results & Matplotlib Failure Anatomy:** [`docs/figure-bench.md`](../../docs/figure-bench.md)
- **External Benchmarks & Outside-Data Adapter:** [`EXTERNAL_BENCHMARKS.md`](EXTERNAL_BENCHMARKS.md) + [`external_bridge.py`](external_bridge.py)
- **Open Leaderboard & Visual Explorer:** [`site/index.html`](site/index.html) (zero-CDN static page)
- **Human Blind Reader Study App:** [`human_study/index.html`](human_study/index.html) (exact `700 px` / `450 px` display-width lock)
- **5-Minute Contributor Guide:** [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## Benchmark Architecture: 100 Tasks · 3 Splits · 6 Tracks

Every task is a realistic conversation (`context.md`), compact deterministic dataset(s) in
`data/`, and a canonical `rubric.json` (`schema_version: "0.1"`) with 3 structured blind-reader
questions (`primary`, `uncertainty`, `nuance`). Prompts never mention `mintfig` or any specific
library (enforced automatically by `bench.py validate-tasks`).

### Splits

| Split | Directory | Tasks | Purpose |
| :--- | :--- | ---: | :--- |
| **`dev`** | `tasks/` | 25 | Open development & iteration across all 6 tracks |
| **`public-test`** | `public_test/` | 50 | Public evaluation suite for open leaderboard comparisons |
| **`heldout`** | `heldout/` | 25 | Held-out generalization split (never used to tune `mintfig` or `SKILL.md`) |
| **Total** | | **100** | |

### Tracks

| Track | ID | Tasks | Splits (`dev`/`pt`/`held`) | What It Evaluates |
| :--- | :--- | ---: | :---: | :--- |
| **Science & Uncertainty** | `science_uncertainty` | 28 | 10 / 10 / 8 | Multi-seed ablations, dose-response, meta-analysis forests, survival curves, reliability diagrams, Bland–Altman agreement, XRD/Raman spectra, CRISPR ranks, climate ensembles, PK profiles, catalyst tradeoffs |
| **SWE & Quantitative Coding** | `swe_coding` | 22 | 5 / 12 / 5 | Latency tails, GPU rooflines, DB query tails, cache MRCs, LLM serving SLAs, `hyperfine` & `pytest-benchmark` diffs, CI timelines & flake heatmaps, cloud cost waterfalls, GC pause tails, distributed scaling |
| **Epistemic Traps & Refusals** | `epistemic_traps` | 18 | 4 / 10 / 4 | Overlapping CIs, no-effect traps, multiple testing, Simpson's paradox, ecological fallacy, survivorship bias, dual-axis spurious trends, heavy-tail means, denominator shifts, cherry-picked windows, truncated-bar bait |
| **Multi-Turn Figure Editing** | `multiturn_edit` | 11 | 3 / 6 / 2 | Targeted revisions to a prior figure: per-capita normalization, splitting confounders, sorting & SLA lines, replacing pies, exposing bimodal tails, switching baselines, log-scale transforms, excluding QC faults |
| **Multi-Surface Delivery** | `multi_surface` | 11 | 2 / 6 / 3 | Legible delivery across `450 px` narrow phone/IDE sidebars, `1280 px` slides, dark NOC/dashboard cards, HTML reports, and 72-column SSH terminal sessions |
| **BYO-Matplotlib Repair** | `byo_repair` | 10 | 1 / 6 / 3 | Repairing broken existing Matplotlib scripts with wrong claims, `jet`/`rainbow` colormaps, truncated bars, dual-axis spaghetti, clipped pies, mislabelled SEM bars, and struck labels |

### Timing Capture

Every run captures full per-task and per-attempt timing automatically:
- **Per attempt (`state.json` & `.bench/timing.json`):** `submitted_iso`, `finished_iso`, `think_s` (agent reasoning/coding time before submit), `render_s`, `script_exec_s`, `audit_s`, `mint_check_s`, `checks_s`, `delivery_check_s`, `submit_total_s`, and cumulative `elapsed_s`.
- **Sweep & CLI telemetry (`sweep_timing.json`, `sweep_timings.json`, `results.json`):** `start_s`, `agent_wall_s`, `wall_s`, plus parsed agent CLI timing (`cli_duration_s`, `cli_api_duration_s`, `ttft_s`, `num_turns`, `total_cost_usd`, token counts) and full distribution summaries (`min`, `p25`, `median`, `mean`, `p75`, `p90`, `p95`, `max`, `total`) by run, split, and track.

---

## Library-Agnostic Scoring

Every submission — regardless of plotting library — is graded across four automated
dimensions plus optional blinded reader evaluation:

1. **Visual Quality (`visual_quality`, 0–100):**
   - For Matplotlib-backed runs, `neutral.py` hooks `Figure.savefig` without importing
     `mintfig` and checks text legibility (`>= 11 px` at target display width), text overlap,
     text crossed by lines, malformed text (`%%`, doubled words, `nan`/`None`; ASCII hyphen
     minus is reported separately as an advisory in `text_advisories`), and canvas-edge clipping.
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

## Full 100-Task Sweep Results (`v0.1`, 2026-11-26)

300 fresh isolated Claude Sonnet 5.5 runs (`25 dev` + `50 public-test` + `25 heldout`; global hooks/MCP disabled):

| Submission (`all`, 100 tasks) | Library | Hook | First-Submit Clean | Zero-Defect (Final) | Text >= 11 px | Right Headline # | Visual Quality | Claim Accuracy | Uncertainty | Median Time | Composite |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `v01-all100-mintfig-sonnet55` | `mintfig` | ON | **87/100 (87.0%)** | **100/100 (100%)** | **100/100 (100%)** | **97/100 (97.0%)** | **99.0** | **97.5** | **95.5** | **11.7 s** | **98.0** |
| `v01-all100-matplotlib-hook-sonnet55` | `matplotlib` | ON | 57/100 (57.0%) | **91/100 (91.0%)** | **100/100 (100%)** | 73/100 (73.0%) | 98.0 | 87.0 | 92.5 | 13.9 s | **93.9** |
| `v01-all100-matplotlib-plain-sonnet55` | `matplotlib` | OFF | 31/100 (31.0%) | 35/100 (35.0%) | 49/99 (49.5%) | 64/99 (64.6%) | 78.8 | 76.5 | 92.9 | **10.9 s** | **84.2** |

### Timing Breakdown Across the 300 Runs (Median / Mean / p90)

| Arm (100 tasks) | Total Task (s) | First Submit (s) | Agent Think (s) | Render + Audit (s) | CLI API (s) | TTFT (s) | Arm Wall (8w) | Mean Cost |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **`mintfig`** | **11.7** / 13.3 / 20.3 | 10.6 / 11.2 / 14.7 | 10.5 / 11.9 / 17.4 | 0.63 / 0.82 / 1.55 | 12.2 / 13.2 / 19.2 | 1.81 | 218.0 s | \$0.076 |
| **`matplotlib-hook`** | 13.9 / 14.8 / 21.9 | 11.1 / 11.2 / 14.2 | 13.2 / 13.9 / 20.7 | 0.61 / 0.90 / 1.56 | 14.6 / 15.3 / 22.6 | 1.51 | 234.1 s | \$0.056 |
| **`matplotlib-plain`** | **10.9** / 11.2 / 14.7 | 10.5 / 10.8 / 13.9 | 10.4 / 10.6 / 13.5 | 0.46 / 0.55 / 0.71 | 11.9 / 12.1 / 15.0 | 1.52 | 183.5 s | \$0.044 |

Reproduce the full 100-task sweep and leaderboard export:

```bash
python evals/figure_bench/run_sweep.py --arms mintfig,matplotlib-plain,matplotlib-coached,matplotlib-hook \
    --run-prefix evals/figure_bench/runs/v01_100_sonnet55 --split all --model sonnet --workers 8
python evals/figure_bench/bench.py export-submission --run evals/figure_bench/runs/v01_100_sonnet55_mintfig \
    --out evals/figure_bench/leaderboard/submissions/my_run.json \
    --submission-id my-run --model "Claude Sonnet 5.5" --split all
```

---

## Initial Seed Results (`v0.1-initial-15`, Historical Baseline)

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
- **What we still need to measure:** Full 100-task runs across multiple models, the
  `matplotlib-coached` prompt-only baseline, additional plotting libraries (`seaborn`,
  `altair`, `plotly`, `ggplot2`), and **display-width-locked human blind reader studies**
  via [`human_study/index.html`](human_study/index.html).

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

### 3. Run built-in agent arms (`mintfig`, `matplotlib`, `matplotlib-coached`, `matplotlib-hook`, `matplotlib-plain`, `custom`)

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
