# mintfig Visual Gallery

Every primary function, visual theme, color palette, and publication plate in `mintfig`, rendered directly from the deterministic scripts in this folder (all datasets are synthetic).

| Section | Jump to |
| :--- | :--- |
| **Highlights** | [Editorial Masterpiece](#editorial-masterpiece-3-panel-briefing) · [Editorial × Terminal Braille](#editorial--24-braille-terminal) · [Terminal Braille & True-Color](#terminal-braille--true-color-gallery) |
| **Conversation Forms (`mint.explain`)** | [`mint.explain`](#mintexplain--multi-panel-arguments) · [`mint.compare`](#mintcompare--size-and-intervals) · [`mint.trend`](#minttrend--change-over-time-dose-or-scale) · [`mint.change`](#mintchange--paired-before-and-after) · [`mint.distribution`](#mintdistribution--raw-observations-and-spread) · [`mint.histogram`](#minthistogram--binned-distributions) · [`mint.relate`](#mintrelate--two-continuous-measures) · [`mint.share`](#mintshare--part-of-a-whole) · [`mint.matrix`](#mintmatrix--two-categorical-dimensions) · [`mint.forest`](#mintforest--effect-sizes-and-meta-analysis) · [`mint.table`](#minttable--exact-lookups-and-scorecards) · [`mint.card`](#mintcard--pr-and-release-kpi-summary-cards) · [Agent Workflow Forms & Briefings](#agent-workflow-forms--multi-turn-briefings) · [Visual-Science & Harness Delivery](#visual-science--harness-adaptive-delivery) · [Table-Graphics & Words on Marks](#table-graphics-words-on-marks--compact-density) · [Model Release Hero Charts](#model-release-hero-charts) |
| **Themes, Palettes & CLI** | [Themes (`style=`)](#themes-style) · [Color Palettes (`palette=`)](#color-palettes-palette) · [Editing & CLI (`mint.load`)](#editing-returned-figures-and-cli) |
| **Publication Plates** | [Before vs. After](#before-vs-after-default-matplotlib) · [Journal Switch](#one-line-journal-switch-nature-183-mm-vs-science-184-mm) · [Multi-Panel Plates](#multi-panel-publication-plates) · [CVD Proof Sheet](#automated-cvd--grayscale-proof-sheet-platebundle) |

---

## Editorial Masterpiece (3-Panel Briefing)

One `mint.explain(..., style="prism", density="compact", width="slide")` call combining a log-scale ECDF with labeled `p50`/`p95` guides, a deterministic beeswarm with tabular medians, and a clean booktabs table-graphics scorecard (in-cell CI whiskers, shared-scale bars, and 7-day rollout sparklines):

![Three-panel checkout latency canary combining log-scale ECDF, beeswarm raw traces, and a table-graphics scorecard](output/readme_comparison/repo_header_hero.png)

### Matching 116-Column 3-Panel 2×4 Dot-Matrix Counterpart (`--matrix`)

The exact same three panels rendered in high-resolution 2×4 Unicode dot-matrix + 24-bit ANSI (`style="obsidian"`, `mode="matrix"`) with 1:1 color alignment (`v2 Cached` mint, `v2 Uncached` arctic sky, `v1 Baseline` off-white):

![116-column 3-panel 2x4 dot-matrix terminal counterpart of the checkout latency canary](output/readme_comparison/repo_header_braille.png)

### Promoted Curated Surface Themes (`style=`)

Same three-panel figure rendered with one-word built-in styles — zero custom `Theme(...)` boilerplate:

| `style="folio"` (`#FFFFFF` editorial serif) | `style="nordic"` (`#F8FBFA` whisper-mint) |
| :---: | :---: |
| ![folio editorial serif edition](output/palette_matching/npg_editorial_serif.png) | ![nordic whisper-mint edition](output/palette_matching/nordic_emerald_slate.png) |
| **`style="obsidian"` (`#0F1715` dark mode)** | **`style="monograph"` (`#FAF7F0` archival serif)** |
| ![obsidian dark mode edition](output/palette_matching/pine_obsidian_dark.png) | ![monograph archival serif edition](output/palette_matching/monograph_ivory_serif.png) |

*Generator: [`make_repo_header.py`](make_repo_header.py)*

---

## Editorial × 2×4 Braille Terminal

One `mint.explain()` call renders as an editorial graphic (masthead accent bar, uppercase kicker, DP-balanced serif headline, inline above-gridline y-ticks) or as a color-aligned 2×4 Unicode Braille + 24-bit ANSI terminal view with zero image viewer needed:

![Same mint.explain() call rendered in editorial style and 2x4 Braille dark terminal](output/readme_comparison/flagship_editorial_braille.png)

*Generator: [`make_flagship_and_03_gallery.py`](make_flagship_and_03_gallery.py)*

---

## `mint.explain` — Multi-panel arguments

Combine 2–4 panels when an argument has steps (*what*, *since when*, *how spread*, *so what*). One entity name keeps one colour across every panel, and `fig.save()` returns computed `facts` per panel to verify the takeaway.

### Two-panel scientific ablation (`mint.compare` + `mint.trend`)

![Ablation study with 95% CIs and training curves](output/explain_science/ablation.png)

*Generator: [`explain_science_examples.py`](explain_science_examples.py)*

### Three-panel materials optimum (`mint.compare` log + `mint.trend` Arrhenius + `mint.compare`)

![Doping optimum across conductivity, Arrhenius curves, and activation energy](output/explain_science/doping_optimum.png)

*Generator: [`explain_science_examples.py`](explain_science_examples.py)*

### Four-panel regression story (`mint.compare` + `mint.trend` + `mint.distribution` + `mint.share`)

![Four-panel latency regression story](output/explain/checkout_story.png)

*Generator: [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `mint.compare` — Size and intervals

Sorted bars from zero by default; switches automatically to dots with whiskers when `error=`, `zero=False`, or `log=True` is passed. Use `baseline=` to draw a control in ink and state every highlighted item against it in `facts`, and `n=` to show sample counts under each name.

### Signed effects with 95% CIs, `n=`, `baseline=`, and `reference=`

![Signed treatment effect compare plot with 95% CIs and n counts](output/explain_forms/compare_intervals.png)

```python
mint.explain(
    "High-dose therapy cuts HbA1c by 1.4 points, 1.6 points below placebo",
    mint.compare(
        {"High dose": -1.4, "Standard dose": -0.7, "Low dose": -0.3,
         "Diet only": -0.1, "Placebo": 0.2},
        error={"High dose": (-1.7, -1.1), "Standard dose": (-1.0, -0.4),
               "Low dose": (-0.6, 0.0), "Diet only": (-0.4, 0.2), "Placebo": (-0.1, 0.5)},
        error_label="95% CI",
        n={"High dose": 62, "Standard dose": 60, "Low dose": 58, "Diet only": 55, "Placebo": 61},
        reference=(0, "no change"), baseline="Placebo", highlight="High dose",
        sort="asc", label="Change in HbA1c at 24 weeks", unit="%", fmt="+.1f",
        title="Both active doses stay well below zero",
    ),
    source="synthetic example data",
)
```

*Generator: [`explain_form_gallery.py`](explain_form_gallery.py)*

### Ranked bars paired with a timeline (`mint.compare` + `mint.trend`)

![Latency regression compare bars and trend](output/explain/latency_regression.png)

*Generator: [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `mint.trend` — Change over time, dose, or scale

Direct end labels (no legend), vertical `events=` markers, missing-value gaps, shaded uncertainty `band=`, raw observations via `points=` (with custom `points_label=`), log axes (`log=`, `log_x=`), and small multiples (`facet=True`).

### ISO dates, `events=`, `baseline=`, and a missing-data gap

![ISO-date trend with retrofit event marker, baseline control, and gap](output/explain_forms/trend_dates_events.png)

```python
mint.explain(
    "The insulation retrofit cut Lab annex daily power use by 28%; the Gym stayed flat",
    mint.trend(
        dates,
        {"Lab annex": [418, 425, 412, None, 298, 304, 295, 301],
         "Library": [360, 355, 362, 358, 296, 291, 298, 294],
         "Gym (control)": [285, 290, 282, 288, 284, 279, 286, 281]},
        baseline="Gym (control)", highlight=["Lab annex", "Library"],
        events={"2026-01-25": "retrofit"},
        label="Daily electricity use", unit="kWh", x_label="Week",
        title="Both retrofitted buildings dropped immediately after Jan 25",
    ),
    note="Lab annex meter was offline during the Jan 25 switchover week.",
    source="synthetic example data",
)
```

*Generator: [`explain_form_gallery.py`](explain_form_gallery.py)*

| Log-log power-law scaling (`log=True, log_x=True`) | Individual observations (`points=` + `points_label=`) |
| :---: | :---: |
| ![Log-log scaling trend](output/explain_forms/trend_log_log.png) | ![Trend with individual task dots](output/explain_forms/trend_points_tasks.png) |
| **Triplicate wells on log dose (`points=`, `log_x=True`)** | **Small multiples (`facet=True`) for > 4 series** |
| ![Dose-response curves](output/explain_science/dose_response.png) | ![Faceted regional orders](output/explain/regional_orders.png) |

*Generators: [`explain_form_gallery.py`](explain_form_gallery.py), [`explain_science_examples.py`](explain_science_examples.py), [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `mint.change` — Paired before and after

Slopegraph pairing two named states (`before`, `after`), showing absolute deltas inline and automatically wrapping in narrow columns.

![Paired benchmark accuracy slopegraph](output/explain/benchmark_gains.png)

```python
mint.explain(
    "The new model gains most where the old one was weakest: +50 points on AIME",
    mint.change(
        before, after,
        labels=("Prior", "New"), label="Accuracy", unit="%", highlight="AIME",
    ),
    source="synthetic example data",
)
```

*Generator: [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `mint.distribution` — Raw observations and spread

Every observation drawn as a dot with a median (or `stat="mean"`) mark and middle-half (IQR) or ± 1 s.d. bar, plus sample counts `n=` and automatic range-separation facts.

### Log-scale fold changes with `baseline=` and `reference=`

![Log-scale gene expression distribution with baseline and reference](output/explain_forms/distribution_log.png)

```python
mint.explain(
    "Drug treatment activates p53 targets (median 2.75×) and halves proliferation genes",
    mint.distribution(
        groups,
        log=True, baseline="Housekeeping", highlight=["p53 targets", "Proliferation"],
        reference=(1.0, "no change"), label="Expression fold change", unit="×",
        title="Every p53 target rises while every proliferation gene falls",
    ),
    subtitle="Bulk RNA-seq, 24 h post-treatment; each dot is one gene",
    source="synthetic example data",
)
```

### Deterministic beeswarm with tabular readout (`mint.distribution(..., mode="swarm")`)

![Dot strip vs deterministic beeswarm with right-aligned median readout column](output/explain_forms/distribution_swarm.png)

### Empirical CDF tail comparison (`mint.distribution(..., mode="ecdf")`)

![Log-scale ECDF latency comparison with p50/p95/p99 reference lines and direct end labels](output/explain_forms/ecdf_latency.png)

```python
mint.explain(
    "v2 Cached cuts p95 latency by 4.5x and keeps 100% of traffic under the 250 ms SLO",
    mint.distribution(
        {"v1 Baseline": v1, "v2 Uncached": v2_uncached, "v2 Cached": v2_cached},
        mode="ecdf", log=True, baseline="v1 Baseline", highlight="v2 Cached",
        reference=(250.0, "SLO 250 ms"), label="Request latency", unit="ms",
    ),
    subtitle="Synthetic request latencies (n=180 per deployment), log scale",
)
```

### Small-n perturbation paired with mechanism (`mint.distribution` + `mint.relate`)

![Gene knockout migration distance distribution and speed-area scatter](output/explain_science/knockout.png)

*Generators: [`explain_form_gallery.py`](explain_form_gallery.py), [`explain_science_examples.py`](explain_science_examples.py)*

---

## `mint.histogram` — Binned distributions

First-class alias for `mint.distribution(..., bins=...)`. Pass a single sequence for a histogram with automatic modal-bin and `% above reference` facts, or a dict of up to 4 groups for stacked shared-axis histograms (never muddy overlapping translucent bars).

### Single-variable bimodal histogram (`mint.histogram`)

![Bimodal request latency histogram with median and SLA threshold](output/explain_forms/histogram_bimodal.png)

```python
mint.explain(
    "Request latency splits into two modes near 18 ms and 44 ms; 32% exceed the 35 ms SLA",
    mint.histogram(
        latencies,
        bins=18,
        reference=(35.0, "35 ms SLA"),
        label="Response time",
        unit="ms",
        title="Cache hits cluster around 18 ms while misses peak near 44 ms",
    ),
    subtitle="220 sampled API requests over 1 hour; dashed line marks overall median",
    source="synthetic example data",
)
```

### Multi-group stacked histograms (`mint.distribution(..., bins=16)`)

![Shared-axis stacked histograms comparing Before and After cohorts](output/explain_forms/histogram_groups.png)

```python
mint.explain(
    "The new checkout flow cuts median latency by 120 ms and drops >500 ms sessions from 34% to 3%",
    mint.distribution(
        {"Before": before, "After": after},
        bins=16,
        baseline="Before",
        highlight="After",
        reference=(500.0, "500 ms target"),
        label="Session latency",
        unit="ms",
        title="Both the centre and the slow right tail shifted left",
    ),
    source="synthetic example data",
)
```

*Generator: [`explain_form_gallery.py`](explain_form_gallery.py)*

---

## `mint.relate` — Two continuous measures

Scatter plot with optional `groups=` (up to 4, directly labelled), `names=` (call out specific points with `highlight=`), `fit=True` least-squares lines with computed `r`, `n`, and 95% slope CIs, and `log_x=`/`log_y=`.

| Grouped scatter with per-group fits & 95% slope CIs | Log-log scatter with fitted power law & named points |
| :---: | :---: |
| ![Hall-Petch grouped scatter](output/explain_forms/relate_groups_fit.png) | ![Log-log allometry scatter](output/explain_forms/relate_log_allometry.png) |

```python
mint.explain(
    "All three alloys follow Hall–Petch; Cu–Zn strengthens 2.3× faster than pure Cu",
    mint.relate(
        inv_sqrt_d, yield_mpa,
        groups=alloy, fit=True, highlight="Cu–Zn",
        x_label="d⁻½ (µm⁻½)", y_label="Yield strength (MPa)", unit="MPa",
        title="Grain refinement pays off steepest in Cu–Zn (r = 0.97)",
    ),
    source="synthetic example data",
)
```

*Generator: [`explain_form_gallery.py`](explain_form_gallery.py)*

---

## `mint.share` — Part of a whole

Sorted percentage bars (never a pie), folding smaller parts past `top=` into one muted `"Other (n)"` bar while reporting the total and combined highlighted share in `facts`.

![Build time share bars with folded Other category](output/explain/build_time.png)

```python
mint.explain(
    "Three stages take 82% of the build: compile, integration tests and image push",
    mint.share(
        stages,
        label="build time", unit="s",
        highlight=["compile", "integration tests", "image push"], top=6,
    ),
    source="synthetic example data",
)
```

*Generator: [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `mint.matrix` — Two categorical dimensions

Heat table with a number in every cell, automatic high-contrast text colour, highlighted cells/rows/columns, diverging ramps (`diverging=True`) for signed/correlation data, and centred em-dash (`—`) markers for missing (`NaN`) cells.

| Sequential with outlier highlight | Missing (`NaN`) cells as `—` |
| :---: | :---: |
| ![Agent task solve rate matrix](output/explain/agent_matrix.png) | ![Matrix with missing cell dashes](output/explain_forms/matrix_missing.png) |

### Row-normalized confusion matrix (`normalize="row", show_counts=True`)

![Row-normalized confusion matrix with percentages and raw counts](output/explain_forms/confusion_matrix_normalized.png)

```python
mint.explain(
    "Issue classifier hits 84% macro accuracy; Feature-to-Bug (11%) is the main confusion",
    mint.matrix(
        counts, rows=classes, cols=classes,
        normalize="row", show_counts=True, label="Predicted class",
    ),
    subtitle="True class (rows) vs predicted class (columns), n=350 test issues",
    palette="berry",
)
```

### Diverging correlation matrix (`diverging=True`)

![Diverging Pearson correlation matrix across materials descriptors](output/explain_science/descriptor_correlations.png)

*Generators: [`explain_chat_examples.py`](explain_chat_examples.py), [`explain_form_gallery.py`](explain_form_gallery.py), [`explain_science_examples.py`](explain_science_examples.py)*

---

## `mint.forest` — Effect sizes and meta-analysis

Aligned cohort or study rows with `sqrt(n)`-scaled point estimates, horizontal CI whiskers against a dashed null line (`reference=0.0` or `1.0`), optional pooled summary diamond (`pooled=`), and right-aligned tabular `est [lo, hi]` + `n` columns.

![Effect-size forest plot with pooled diamond and right-aligned CI and n columns](output/explain_forms/forest_ab_meta.png)

```python
mint.explain(
    "Checkout v3 leads a +2.3 pp pooled conversion lift across four winning cohorts",
    mint.forest(
        effects, error=cis, error_label="95% CI",
        pooled={"label": "Pooled", "value": 2.3, "lo": 1.6, "hi": 3.0, "n": 18400},
        n=sample_sizes, highlight="Checkout v3",
        label="Conversion lift", unit="pp",
    ),
    subtitle="Fixed-effects A/B rollout across six cohorts (n=18,400 total sessions)",
    palette="mint",
)
```

---

## `mint.table` — Exact lookups and scorecards

Booktabs-styled tables with proportional column widths, per-column `units=`, mixed `fmt=`, auto-bolded column winners (`bold_best=`), shared entity row `highlight=`, `baseline=` deltas in `facts`, `—` for missing cells, and `panel.to_markdown()` export. Accepts `list[dict]`, DataFrames, column dicts, or 2-D lists.

![Chat-width compare and booktabs benchmark scorecard sharing entity colours](output/explain_release/table_scorecard_chat.png)

```python
mint.explain(
    "Alpha-3 leads every reasoning benchmark while costing 17% less than Alpha-2",
    mint.compare(rows, name="Model", value="GPQA", title="GPQA Diamond", label="Accuracy", unit="%",
               highlight="Alpha-3", baseline="Alpha-2"),
    mint.table(
        rows,
        units={"GPQA": "%", "SWE-bench": "%", "AIME": "%", "Cost": "$/M"},
        bold_best={"GPQA": "max", "SWE-bench": "max", "AIME": "max", "Cost": "min"},
        highlight="Alpha-3", baseline="Alpha-2", sort="-GPQA",
        fmt={"GPQA": ".1f", "SWE-bench": ".1f", "AIME": ".0f", "Cost": "${:.2f}"},
        title="Full benchmark scorecard",
    ),
    layout=[["a"], ["b"]],
    source="synthetic model evaluation data",
)
```

---

## `mint.card` — PR and release KPI summary cards

Compact KPI strip (bold values, color-coded deltas, and inline sparklines) paired with an optional `mintfig` panel. Call `.save("card.png")` for a single image, `.save_pair("pr_card")` for a GitHub `<picture>` light/dark pair, or run `mintfig card spec.json --out card.png --pair`.

| Light PR summary card | Dark PR summary card |
| :---: | :---: |
| ![Light PR summary card with sparklines and compare panel](output/explain_release/pr_card_light.png) | ![Dark PR summary card with sparklines and compare panel](output/explain_release/pr_card_dark.png) |

```python
card = mint.card(
    "PR #418 cuts checkout p99 latency 38% while holding 99.94% availability",
    [
        {"label": "p99 latency", "value": "248 ms", "delta": "-38%", "good": True, "spark": [400, 395, 390, 385, 305, 270, 248]},
        {"label": "Availability", "value": "99.94%", "delta": "+0.02 pts", "good": True, "spark": [99.91, 99.92, 99.92, 99.93, 99.93, 99.94, 99.94]},
        {"label": "Error rate", "value": "0.06%", "delta": "-0.04 pts", "good": True, "spark": [0.10, 0.09, 0.09, 0.08, 0.07, 0.06, 0.06]},
        {"label": "Peak RSS", "value": "412 MB", "delta": "+18 MB", "good": False, "spark": [394, 396, 397, 396, 408, 411, 412]},
    ],
    panel=mint.compare({"checkout": 248, "payment": 195, "cart": 142, "catalog": 98, "health": 24},
                       label="p99 latency", unit="ms", highlight="checkout", title="p99 latency by endpoint"),
    subtitle="checkout-service canary · 7-day window (n = 1.2M requests)",
    source="perf-canary 2026-11 · 5 clusters",
)
card.save_pair("pr_card")  # writes pr_card_light.png + pr_card_dark.png + GitHub <picture> Markdown
```

---

## Agent Workflow Forms & Multi-Turn Briefings

Forms and workflows designed for recurring agent-to-human explanations: attribution bridges (`mint.waterfall`), execution span traces (`mint.timeline`), cohort/pipeline attrition funnels (`mint.flow`), fitted scaling curves (`trend(fit=)`), lower-triangle correlation matrices (`matrix(triangle="lower", mask_diagonal=True)`), persistent multi-turn entity colours (`mint.Session`), and cohesive zero-CDN HTML & Markdown briefings (`mint.brief` / `mintfig brief`).

### Attribution bridge (`mint.waterfall`)

![Ablation attribution bridge from base model to shipped candidate](output/explain_workflows/01_ablation_waterfall.png)

### Execution & milestone span timeline (`mint.timeline`)

![Grouped CI execution trace with parallel lanes, milestone diamond, and SLA reference line](output/explain_workflows/02_ci_timeline.png)

### Sequential cohort / pipeline attrition funnel (`mint.flow`)

![Clinical cohort attrition funnel with step-down drop counts, percentages, and exclusion reasons](output/explain_workflows/03_cohort_flow.png)

### Regression fits (`trend(fit=True)`) & lower-triangle correlation matrix (`triangle="lower", mask_diagonal=True`)

| Power-law & linear regression overlays (`trend(fit=)`) | Lower-triangle masked-diagonal correlation matrix |
| :---: | :---: |
| ![Power-law and linear regression fits on trend panels](output/explain_workflows/04_scaling_trend_fit.png) | ![Lower-triangle correlation matrix with masked diagonal](output/explain_workflows/05_corr_matrix_triangle.png) |

### Multi-turn visual memory (`mint.Session`) & dark serving bridge (`mint.brief` export)

![Dark theme multi-turn Session figure preserving Alpha-3 and Beta-Pro colours across variants alongside a serving cost bridge](output/explain_workflows/06_session_memory_dark.png)

*Generator: [`explain_agent_workflow_examples.py`](explain_agent_workflow_examples.py) (also outputs [`06_investigation_brief.html`](output/explain_workflows/06_investigation_brief.html) and [`06_investigation_brief.md`](output/explain_workflows/06_investigation_brief.md)).*

---

## Visual-Science & Harness-Adaptive Delivery

Grounded in empirical visual communication research (Kay & Hullman quantile dotplots & nested CIs, Franconeri et al. direct delta encoding & spatial contiguity, Segel & Heer narrative callouts, Lundgard & Satyanarayan L1–L4 narratives, Kong et al. tightly scoped epistemic slant checks) and adapted to how real agent harnesses display visuals (`width="narrow"` for IDE sidebars, `fig.save("out.html")` interactive SVG+JS, and `mintfig show` for Kitty/iTerm2/Unicode terminals).

### Quantile dotplots (`mode="quantile"`) + nested 50%/95% CIs (`inner_error=`) & inline baseline deltas (`show_delta=True`)

![Quantile dotplot with 5% countable dots paired with nested 50%/95% CIs and inline deltas](output/explain_visual_science/uncertainty_quantile_nested_ci.png)

### Shaded `regions=` and collision-checked leader-arrow `callouts=` across `trend` and `relate`

![Trend and scatter panels with shaded regions and direct leader-arrow callouts](output/explain_visual_science/narrative_callouts_regions.png)

### IDE sidebar preset (`width="narrow"`, 450 px auto-stacked)

<img src="output/explain_visual_science/harness_narrow_sidebar.png" width="450" alt="Narrow 450 px IDE sidebar figure with auto-stacked panels and inline baseline deltas">

*Generator: [`explain_visual_science_examples.py`](explain_visual_science_examples.py)*

---

## Table-Graphics, Words on Marks & Compact Density

- **In-cell table graphics (`mint.table(bars=, interval=, spark=)`)**: shared-scale latency bars, 95% CI whiskers, and training sparklines right beside each number.
- **Words on marks & auto delta brackets (`color_names=True`, `show_delta="auto"`, `density="compact"`)**: entity names in the serif headline inherit their mark's colour, stated differences draw clean brackets automatically, and `density="compact"` tightens row height while holding type size steady.

| In-cell table graphics (`bars=`, `interval=`, `spark=`) | Words on marks + auto delta brackets (`density="compact"`) |
| :---: | :---: |
| ![Table-graphics scorecard with 95% CI whiskers, bars, and sparklines](output/explain_forms/table_graphics_scorecard.png) | ![Words on marks editorial figure with auto delta brackets and compact density](output/explain_forms/words_on_marks_compact.png) |

*Generator: [`make_flagship_and_03_gallery.py`](make_flagship_and_03_gallery.py). Also see `summary["deliver"]`, adaptive `fig.save("fig.html")`, and `mint.brief(...)` in the [main README](../README.md).*

---

## Model Release Hero Charts

Combine grouped `mint.compare`, stacked `boost=` extensions, Pareto frontier `mint.relate(frontier=True, label_all=True, connect_groups=True)`, and `mint.table` with `width="slide"` (1280 px display width / 2560 px retina export) and custom `accent="#..."` brand colours.

### Grouped multi-benchmark head-to-head + extended-thinking `boost=` (`style="paper"`, `width="slide"`)

![Warm paper model release hero with grouped benchmarks and stacked extended-thinking bars](output/explain_release/release_benchmarks_paper.png)

### Capability-vs-cost Pareto frontier + scorecard (`style="dark"`, `width="slide"`)

![Dark mode model release hero with Pareto frontier scatter and booktabs scorecard](output/explain_release/release_frontier_dark.png)

*Generator: [`explain_release_examples.py`](explain_release_examples.py)*

---

## Terminal Braille & True-Color Gallery

High-resolution **2×4 Unicode Braille** charts, **24-bit ANSI true-color** heatmaps, side-by-side 2-panel layouts (`width >= 104`), rounded terminal KPI summary cards (`mint.card(...).to_terminal()`), and `mintchip --braille --theme mint_dark` tables — rendered directly from live terminal outputs. **[Full guide with runnable Python & CLI snippets →](../docs/terminal-braille.md)**

![Animated tour of mintfig 2x4 Braille terminal charts, 24-bit true-color matrices, PR KPI cards, and mintchip tables](output/terminal/braille_showcase.gif)

| 1. Training curves with stippled 95% CI bands (`mint.trend`) | 2. Wide 116-col 2-panel ECDF + beeswarm (`layout=[["a", "b"]]`) |
| :---: | :---: |
| ![Braille training curves with stippled 95% CI bands](output/terminal/01_trend_ci_band.png) | ![Wide 116-column side-by-side Braille ECDF and beeswarm](output/terminal/02_wide_ecdf_and_swarm.png) |
| **3. Grouped scatter + OLS fit + Pareto hull (`mint.relate`)** | **4. Paired before/after slopegraph (`mint.change`)** |
| ![Braille scatter with OLS fit and Pareto frontier](output/terminal/03_relate_pareto_fit.png) | ![Paired Braille slopegraph with colored deltas](output/terminal/04_change_slopegraph.png) |
| **5. A/B rollout forest plot with pooled `◆` (`mint.forest`)** | **6. 24-bit ANSI true-color confusion matrix (`mint.matrix`)** |
| ![Braille A/B rollout forest plot with pooled diamond](output/terminal/05_forest_ab_rollout.png) | ![24-bit ANSI true-color row-normalized confusion matrix](output/terminal/06_matrix_confusion_truecolor.png) |
| **7. PR / Release KPI summary card (`mint.card`)** | **8. Shared-scale `mintchip` Braille table (`mint_dark`)** |
| ![Terminal PR KPI summary card with Braille sparklines and trend panel](output/terminal/07_kpi_summary_card.png) | ![mintchip shared-scale Braille benchmark table in mint_dark](output/terminal/08_mintchip_braille_table.png) |

*Generator: [`braille_terminal_gallery.py`](braille_terminal_gallery.py) (also saves raw ANSI captures `output/terminal/01_trend_ci_band.txt` … `08_mintchip_braille_table.txt`).*

---

## Themes & Color Palettes

Every built-in surface theme (`style=`) and color palette (`palette=`) is verified for deuteranopia, protanopia, grayscale luminance separation (`≥ 0.05`), and WCAG 4.5:1 text contrast. Mix and match freely: `mint.explain(..., style="paper", palette="okabe_ito")`.

![Overview of all mintfig color palettes, surface themes, and editorial colormaps](output/explain_themes/palettes_overview.png)

### Themes (`style=`)

The same two-panel comparison + trend rendered across all fifteen built-in surface styles — leading with the five flagship curated editions (`prism`, `folio`, `nordic`, `obsidian`, `monograph`):

| `style="prism"` (`npg` · crisp white sans) | `style="folio"` (`npg_editorial` · white serif) |
| :---: | :---: |
| ![prism theme](output/explain_themes/style_prism.png) | ![folio theme](output/explain_themes/style_folio.png) |
| **`style="nordic"`** (whisper-mint Swiss) | **`style="obsidian"`** (deep pine dark) |
| ![nordic theme](output/explain_themes/style_nordic.png) | ![obsidian theme](output/explain_themes/style_obsidian.png) |
| **`style="monograph"`** (`ivory` · archival serif) | **`style="mintfig"`** (default) |
| ![monograph theme](output/explain_themes/style_monograph.png) | ![mintfig theme](output/explain_themes/style_mintfig.png) |
| **`style="mint"`** (whisper-mint + zero-yellow) | **`style="pine"`** (`mint_dark`) |
| ![mint theme](output/explain_themes/style_mint.png) | ![pine dark theme](output/explain_themes/style_pine.png) |
| **`style="botanical"`** (sage-ivory + serif) | **`style="editorial"`** (newspaper + serif) |
| ![botanical theme](output/explain_themes/style_botanical.png) | ![editorial theme](output/explain_themes/style_editorial.png) |
| **`style="paper"`** (warm ivory + serif) | **`style="bold"`** (matte gray + heavy strokes) |
| ![paper theme](output/explain_themes/style_paper.png) | ![bold theme](output/explain_themes/style_bold.png) |
| **`style="dark"`** (slate charcoal) | **`style="mono"`** (monochrome print + single accent) |
| ![dark theme](output/explain_themes/style_dark.png) | ![mono theme](output/explain_themes/style_mono.png) |

#### `style="sketch"` (hand-drawn illustrative)

![sketch theme](output/explain_themes/style_sketch.png)

### Color Palettes (`palette=`)

All eleven `mint.explain` color palettes shown on a four-series figure (5 zero-yellow mint-inspired palettes first, followed by the 6 classic palettes):

| `palette="mint"` (zero yellow) | `palette="spearmint"` (zero yellow) |
| :---: | :---: |
| ![mint palette](output/explain_themes/palette_mint.png) | ![spearmint palette](output/explain_themes/palette_spearmint.png) |
| **`palette="matcha"`** (zero yellow) | **`palette="glacier"`** (zero yellow) |
| ![matcha palette](output/explain_themes/palette_matcha.png) | ![glacier palette](output/explain_themes/palette_glacier.png) |
| **`palette="mineral"`** (zero yellow) | **`palette="default"`** |
| ![mineral palette](output/explain_themes/palette_mineral.png) | ![default palette](output/explain_themes/palette_default.png) |
| **`palette="okabe_ito"`** | **`palette="tol"`** |
| ![okabe_ito palette](output/explain_themes/palette_okabe_ito.png) | ![tol palette](output/explain_themes/palette_tol.png) |
| **`palette="earth"`** | **`palette="ocean"`** |
| ![earth palette](output/explain_themes/palette_earth.png) | ![ocean palette](output/explain_themes/palette_ocean.png) |

#### `palette="berry"`

![berry palette](output/explain_themes/palette_berry.png)

*Generator: [`explain_theme_palette_gallery.py`](explain_theme_palette_gallery.py) (plus the 6-figure style matrix in [`explain_style_showcase.py`](explain_style_showcase.py) → `output/explain_styles/`).*

---

## Editing returned figures and CLI

Every PNG saved by `mint.explain` embeds its normalized JSON spec. Rebuild and modify a figure without re-deriving the data:

```python
spec = mint.load("ablation.png").to_spec()
spec["style"] = "paper"
spec["palette"] = "okabe_ito"
spec["panels"][0]["highlight"] = ["no fine-tuning"]
print(mint.load(spec).save("ablation_v2.png", write_spec=True))
```

Or from the command line with no Python script:

```bash
mintfig explain --example | mintfig explain - --out latency.png
mintfig explain --show-spec latency.png
mintfig explain latency.png --style dark --palette ocean --out latency_dark.png
```

---

## Publication Figures (`mint.figure`, `mint.Plate`, `mintfig run`)

Exact physical millimetre geometry, uniform sans-serif typography and math, Type 42 vector PDFs, automated CVD + grayscale proof sheets, and reproducible manuscript bundles. See [`benchmark_comparison.md`](benchmark_comparison.md) for the quantitative PDF/preflight audit.

### Before vs. After default Matplotlib

![Before vs After single-column Nature figure](output/before_after_nature.png)

*Generator: [`generate_showcase.py`](generate_showcase.py)*

### One-line journal switch (*Nature* 183 mm vs. *Science* 184 mm)

![Nature vs Science one-line journal switch](output/nature_vs_science.png)

*Generator: [`generate_showcase.py`](generate_showcase.py)*

### Multi-panel publication plates

| *Nature* double-column quantum phase diagram (`183 mm`) | *Science* 3-column exoplanet spectroscopy (`184 mm`) |
| :---: | :---: |
| ![Nature quantum critical dome](output/nature_quantum_critical_dome.png) | ![Science exoplanet atmosphere](output/science_exoplanet_atmosphere.png) |
| [`nature_quantum_critical_dome.py`](nature_quantum_critical_dome.py) | [`science_exoplanet_atmosphere.py`](science_exoplanet_atmosphere.py) |
| **NeurIPS Tufte scaling + slopegraph + sparklines (`139.7 mm`)** | **Cell Press lineage bifurcation (`174 mm`)** |
| ![NeurIPS Tufte plate](output/neurips_frontier_tufte/preview.png) | ![Cell lineage bifurcation](output/cell_lineage_bifurcation/preview.png) |
| [`neurips_frontier_tufte.py`](neurips_frontier_tufte.py) | [`cell_lineage_bifurcation.py`](cell_lineage_bifurcation.py) |

### Automated CVD + grayscale proof sheet (`plate.bundle(...)`)

![Nature 4-panel plate CVD and grayscale proof sheet](output/example2_nature_proof.png)

*More publication plates in this folder: [`masterpiece_1_chaos.py`](masterpiece_1_chaos.py), [`masterpiece_2_omics.py`](masterpiece_2_omics.py), [`masterpiece_3_climate.py`](masterpiece_3_climate.py), [`neurips_frontier_scaling.py`](neurips_frontier_scaling.py).*
