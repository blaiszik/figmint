# mintfig

**Mint-condition figures for AI agents and scientists.**

AI agents are great at running analyses and terrible at showing what they found. `mintfig` turns raw data into clear, self-auditing visual explanations — as a Python library (`import mintfig as mint`), zero-script CLI, and coding-agent skill built on Matplotlib.

1. **Explain results in a conversation (`mint.explain`, `mintfig plot`)** — lead with a takeaway sentence and compose panels by question (comparisons, trends, distributions, attribution bridges, timelines, attrition flows, scorecards). Layout, direct labels, named uncertainty, colorblind-safe themes, drawn-text auditing (`ship`), and computed `facts` are built in — delivered as PNGs, interactive HTML, terminal graphics, or multi-figure briefings (`mint.brief`).
2. **Ship journal-ready manuscript plates (`mint.Plate`, `mintfig run`)** — exact millimeter column geometry, unified sans-serif typography and math, automated preflight QA, colorblind/grayscale proof sheets, and reproducible submission bundles for *Nature*, *Science*, *Cell*, PNAS, and NeurIPS.

[Quickstart](#quickstart) · [Forms at a Glance](#pick-the-form-by-the-question) · [Themes & Palettes](#themes--palettes) · **[Full Visual Gallery](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md)** · [Publication Plates](#publication-figures) · [CLI & Agent Skill](#cli--agent-skill)

---

![Dose-response figure: triplicate wells on a log dose axis, one colour per compound across panels](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_science/dose_response.png)

---

## Quickstart

```bash
pip install mintfig
# or with uv
uv add mintfig
```

Give your coding agent the bundled skill (Claude Code, Antigravity, Cursor, Codex, `AGENTS.md`):

```bash
mintfig skill --install
```

### Explain a result (`mint.explain`)

Write the conclusion first, then pick each panel by the question it answers. `fig.save()` returns a JSON summary containing computed `facts` per panel, any `issues` with a `fix_hint`, `alt_text`, and measured legibility at chat width:

```python
import mintfig as mint

fig = mint.explain(
    "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
    mint.compare(
        {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
        error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77),
               "no fine-tuning": (0.66, 0.72)},
        error_label="95% CI, 5 seeds",
        title="Both losses are outside seed noise",
        label="Test accuracy",
        highlight=["no retrieval", "no fine-tuning"],
    ),
    mint.trend(
        [0, 500, 1000, 1500, 2000],
        {"full model": [0.02, 0.61, 0.76, 0.80, 0.82],
         "no retrieval": [0.02, 0.52, 0.67, 0.72, 0.74],
         "no fine-tuning": [0.01, 0.44, 0.60, 0.66, 0.69]},
        title="The gap opens in the first 500 steps",
        label="Validation accuracy",
        x_label="Training step",
    ),
    source="runs/ablation_2026-11 (5 seeds per variant)",
)
print(fig.save("ablation.png"))
```

No Python script needed? Render directly from JSON or stdin with `mintfig explain`:

```bash
mintfig explain --example | mintfig explain - --style editorial --palette okabe_ito --out fig.png
```

---

## Pick the form by the question

Every form enforces its own perceptual rules (zero baselines, direct labels, no pies, no rotated text, named uncertainty) and computes panel `facts` automatically. **[Browse all 40+ rendered examples with full code in the Gallery →](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md)**

| Form | Question it answers & encoding | Example |
| :--- | :--- | :---: |
| **`mint.compare`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#mintcompare--size-and-intervals)</sub> | **How do items differ in size?**<br>Sorted bars from zero; switches to dots with whiskers for `error=`, `zero=False`, or `log=True`. Supports `n=`, `baseline=`, and `reference=`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/compare_intervals.png" width="380" alt="mint.compare with 95% CIs, n counts, and baseline"> |
| **`mint.trend`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#minttrend--change-over-time-dose-or-scale)</sub> | **How does it change over time, dose, or scale?**<br>Direct end labels, ISO dates, `events=`, gaps, `band=`, raw `points=` (with `points_label=`), `fit=` regression overlays, `log=`/`log_x=` power laws, and `facet=True` small multiples. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/trend_dates_events.png" width="380" alt="mint.trend with ISO dates, retrofit event, baseline, and gap"> |
| **`mint.change`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#mintchange--paired-before-and-after)</sub> | **What moved between two states?**<br>Paired slopegraph with inline deltas; wraps cleanly in narrow columns. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain/benchmark_gains.png" width="380" alt="mint.change paired slopegraph"> |
| **`mint.distribution`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#mintdistribution--raw-observations-and-spread)</sub> | **How are raw observations spread across groups?**<br>Every observation as a dot with a median/IQR (or mean/±1 s.d.) mark, or **quantile dotplots (`mode="quantile"`)** with countable probability dots, exceedance & P(A > B) facts, `n=`, and `log=True`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_visual_science/uncertainty_quantile_nested_ci.png" width="380" alt="Quantile dotplots paired with nested 50%/95% CIs and inline baseline deltas"> |
| **`mint.histogram`**<br><sub>alias: `distribution(bins=)`</sub><br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#minthistogram--binned-distributions)</sub> | **What is the binned shape or modality?**<br>Single-variable or shared-axis stacked histograms (up to 4 groups), dashed centre line, modal bin and `% above reference` facts. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/histogram_bimodal.png" width="380" alt="mint.histogram bimodal distribution with SLA reference"> |
| **`mint.relate`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#mintrelate--two-continuous-measures)</sub> | **Do two continuous measures move together?**<br>Scatter with optional `groups=` (directly labelled), `names=`, `fit=True` least-squares lines with computed `r`, `n`, and 95% slope CIs, plus `log_x=`/`log_y=`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/relate_groups_fit.png" width="380" alt="mint.relate grouped scatter with linear fits"> |
| **`mint.share`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#mintshare--part-of-a-whole)</sub> | **What makes up the total?**<br>Sorted percentage bars (never a pie), folding smaller parts past `top=` into `"Other (n)"` with combined highlight shares in `facts`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain/build_time.png" width="380" alt="mint.share build time breakdown"> |
| **`mint.matrix`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#mintmatrix--two-categorical-dimensions)</sub> | **How do two categorical dimensions interact?**<br>Heat table with a number in every cell, `diverging=True`, `triangle="lower"|"upper"` + `mask_diagonal=True` for symmetric correlations, highlights, and `—` for missing values. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_workflows/05_corr_matrix_triangle.png" width="380" alt="mint.matrix lower-triangle correlation matrix with masked diagonal"> |
| **`mint.table`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#minttable--exact-lookups-and-scorecards)</sub> | **Need exact lookups or a mixed-unit scorecard?**<br>Booktabs table with per-column `units=`, `bold_best=` winners, shared row `highlight=`, `baseline=` deltas in `facts`, `—` for missing cells, and `.to_markdown()`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_release/table_scorecard_chat.png" width="380" alt="mint.table booktabs benchmark scorecard paired with mint.compare"> |
| **`mint.waterfall` / `timeline` / `flow`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#agent-workflow-forms--multi-turn-briefings)</sub> | **Attribution bridges, execution traces, & cohort attrition.**<br>Delta bridges start→total, parallel `[start, end]` pipeline traces with milestones, and sequential attrition funnels with drop reasons. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_workflows/01_ablation_waterfall.png" width="380" alt="mint.waterfall ablation attribution bridge"> |
| **Visual scaffolding**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#visual-science--harness-adaptive-delivery)</sub> | **Point directly at the mechanism & fit every harness.**<br>Shaded `regions=` + leader-arrow `callouts=` on `trend`/`relate`, nested `inner_error=` CIs, `show_delta=True`, `width="narrow"` (450 px IDE sidebars), interactive `fig.save("out.html")`, and `mintfig show` (Kitty/iTerm2/Unicode). | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_visual_science/narrative_callouts_regions.png" width="380" alt="Trend and relate panels with shaded regions and direct callout arrows"> |
| **Release hero cards**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#model-release-hero-charts)</sub> | **Frontier model release & benchmark announcements.**<br>Grouped `mint.compare`, stacked `boost=` extensions, Pareto `mint.relate(frontier=True, label_all=True, connect_groups=True)`, `width="slide"`, and custom `accent=`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_release/release_frontier_dark.png" width="380" alt="Dark mode model release hero with Pareto frontier and scorecard"> |
| **`mint.explain`**<br><sub>[more examples](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#mintexplain--multi-panel-arguments)</sub> | **Tell a multi-step argument in one glance.**<br>Compose 2–4 panels with one shared colour per entity across views, `mint.Session` visual memory, `mint.brief` reports, and embedded spec round-tripping (`mint.load` / `mint.edit`). | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain/checkout_story.png" width="380" alt="mint.explain four-panel regression story"> |

### Built for scientific agents

- **Uncertainty is first class and must be named.** Raw observations (`distribution`, `histogram`, `trend(points=)`), intervals (`compare(error=, error_label=)`), and bands (`trend(band=, band_label=)`); an unlabelled interval triggers a warning.
- **Numbers keep their magnitude.** Values format to ~3 significant figures (`1.3×10⁻⁷` when tiny or huge, never silently rounded to zero) with log axes on `compare`, `trend`, `distribution`, `histogram`, and `relate`.
- **One colour per entity.** A name keeps its colour across every panel of a figure, and `mint.Session` / `colors=` pin hues across turns in a conversation.
- **Facts & one-shot shipping (`summary["ship"]`, `mint.lenient()`).** `fig.save()` returns computed `facts` per panel plus a `"ship"` verdict that separates real visual defects from minor advisory warnings so agents don't burn extra turns re-rendering good-enough figures. For rapid ad-hoc charts, `with mint.lenient():` / `mint.explain(..., strict=False)` / `mintfig explain --lenient` auto-adjusts soft limits (auto-faceting >4 series, auto-stacking cramped panels, trimming oversized lists) instead of rejecting.
- **Errors that teach & figures that come back.** Invalid arguments raise `ExplainError` with the exact fix; every PNG embeds its spec so `mint.edit("fig.png", ...)` / `mint.load("fig.png")` rebuilds and refines returned figures without redrawing from memory.
- **Native data inputs & Unicode.** Dicts, lists, CSV/TSV/JSON/JSONL files (`mint.load_table_file`, `mintfig plot --kind auto`), NumPy arrays, pandas Series and DataFrames, plus direct Unicode symbols (`µm`, `cm⁻³`, `°C`, `χ²`). Full argument reference: [src/mintfig/assets/SKILL.md](https://github.com/blaiszik/mintfig/blob/main/src/mintfig/assets/SKILL.md) (verified by tests against the live API).

---

## Themes & Palettes

Surface **themes (`style=`)** and **color palettes (`palette=`)** change only aesthetics — never the information-design rules. Every built-in theme and palette is quantitatively tested for deuteranopia, protanopia, grayscale luminance separation, and WCAG 4.5:1 text contrast.

![mintfig color palettes, surface themes, and editorial colormaps](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_themes/palettes_overview.png)

- **7 surface themes (`style=`):** `mintfig` (default), `editorial` (serif headline, dotted grids), `paper` (warm ivory ground), `bold` (matte gray, heavy lines), `dark` (charcoal slate for dark UIs & slides), `mono` (monochrome print + single vermilion accent), and `sketch` (hand-drawn for illustrative points).
- **6 `mint.explain` color palettes (`palette=`):** `default`, `okabe_ito`, `tol`, `earth`, `ocean`, and `berry` — mixable with any surface theme (`mint.explain(..., style="paper", palette="okabe_ito")`).

| `style="dark"` | `style="paper"` | `palette="berry"` |
| :---: | :---: | :---: |
| ![dark theme](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_themes/style_dark.png) | ![paper theme](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_themes/style_paper.png) | ![berry palette](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_themes/palette_berry.png) |

**[See all 7 themes and all 6 palettes rendered side-by-side in the Gallery →](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#themes--color-palettes)**

---

### Design rules, and where they come from

| Rule the forms enforce | Basis |
| :--- | :--- |
| The title is the conclusion as a sentence; each panel has its own headline | Assertion–evidence structure (Alley & Neeley, *Technical Communication* 2005) |
| Quantities are encoded by position or length on a common scale; bars start at zero; no pies | Cleveland & McGill, *JASA* 1984 (ranking of elementary perceptual tasks) |
| At most 4 coloured series and 3 highlights; the rest is grey context or small multiples | Working-memory capacity of ~4 items (Cowan, *BBS* 2001); small multiples (Tufte 1983) |
| Labels sit on the data, not in a legend; all text horizontal | Spatial contiguity / split attention (Mayer, *Multimedia Learning*) |
| Raw observations and named intervals are shown rather than hidden in bars | Weissgerber et al., *PLoS Biology* 2015; Cumming et al., *J. Cell Biol.* 2007 |
| A name keeps one colour across panels | Consistency of visual encoding across views (Qu & Hullman, *IEEE TVCG* 2018) |
| Series colours separate under deuteranopia, protanopia, and grayscale; text ≥ 4.5:1 contrast | Machado et al. 2009 simulation; WCAG 2 contrast |
| Text is at least 11 px tall at a 700 px chat column | Legibility floor, measured after layout and reported in the summary |

---

## Publication Figures

Default Matplotlib figures break journal specifications in subtle ways: 6.4" canvases shrink text below 5 pt when scaled to an 89 mm column, `bbox_inches="tight"` mutates PDF MediaBox dimensions, Type 3 fonts break Illustrator editing, Computer Modern serif math clashes with Helvetica labels, and 50k-point scatters produce sluggish multi-megabyte PDFs.

![Before vs After default Matplotlib on an 89 mm Nature single-column figure](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/before_after_nature.png)

- **Exact physical column widths** — locked PDF MediaBox dimensions with `constrained_layout` and versioned journal spec provenance.
- **Uniform sans-serif typography & math** — Helvetica/Arial/Liberation Sans/DejaVu Sans for body text and mathtext, Type 42 PDF embedding (`pdf.fonttype = 42`), editable SVG text (`svg.fonttype = "none"`).
- **Multi-panel `Plate` engine & Tufte primitives** — aligned bold panel labels (`a, b, c` / `A, B, C`), auto-stacked `sig_bracket`, `scalebar`, `direct_labels`, `zoom_inset`, `range_frame`, `ghost_context`, `tufte_boxplot`, `slopegraph`, and `sparkline`.
- **Hybrid vector/raster & byte-reproducible bundles** — `save_figure(..., rasterize_above=10_000)` keeps axes crisp vector while rasterizing dense scatter/mesh layers; `mintfig run --bundle out/` emits `figure.pdf`, `figure.svg`, `preview.png`, `proof.png` (CVD + grayscale scorecard), `figure.tex`, `figure.json`, `reproduce.py`, and `report.json`.

**[View the Nature, Science, Cell, and NeurIPS publication plates in the Gallery →](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#publication-figures-mintfigure-mintplate-mintfig-run)** · [8-dimension journal audit](https://github.com/blaiszik/mintfig/blob/main/gallery/benchmark_comparison.md)

### Supported journal & screen specs

| Target | Width Presets (mm) | Max Height (mm) | Body / Tick / Panel | Panel Case | Default Palette | Combo / Line DPI |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Nature Portfolio** (`nature`) | `single`: 89, `mid`/`1.5col`: 120, `double`/`full`: 183 | 170 (247 page) | 6.5 / 6.0 / 8.0 pt | `a, b, c` | `nature` | 500 / 1000 |
| **Science (AAAS)** (`science`) | `single`: 55, `double`/`2col`: 120, `full`/`3col`: 184 | 180 (230 page) | 7.0 / 6.0 / 8.5 pt | `A, B, C` | `science` | 600 / 1200 |
| **Science Advances** (`science_advances`) | `single`: 84, `mid`: 120, `double`/`full`: 175 | 180 (230 page) | 7.0 / 6.0 / 8.5 pt | `A, B, C` | `science` | 600 / 1200 |
| **Cell Press** (`cell`) | `single`: 85, `mid`/`1.5col`: 114, `double`/`full`: 174 | 200 (230 page) | 7.0 / 6.0 / 8.5 pt | `A, B, C` | `nature_muted` | 500 / 1000 |
| **PNAS** (`pnas`) | `single`: 87, `mid`/`1.5col`: 114, `double`/`full`: 178 | 200 (225 page) | 7.0 / 6.5 / 9.0 pt | `A, B, C` | `nature_muted` | 600 / 1200 |
| **NeurIPS** (`neurips`) | `half`/`single`: 67, `mid`: 111.8, `double`/`full`: 139.7 | 180 (228.6 page) | 7.5 / 6.5 / 8.5 pt | `a, b, c` | `nature_muted` | 500 / 1000 |
| **Screen / Chat** (`screen`) | `chat`/`single`: 140, `wide`/`double`: 180, `slide`: 240 | 135 (160 page) | 8.5 / 7.5 / 10.0 pt | `a, b, c` | `nature_muted` | 220 / 300 |

### Publication quickstart

```python
import numpy as np
import mintfig as mint


def build(journal: str = "nature") -> mint.Plate:
    plate = mint.Plate(journal=journal, width="double", height_mm=118.0, layout=[["a", "b"], ["c", "d"]])
    x = np.linspace(0, 10, 200)
    plate["a"].plot(x, np.exp(-x / 3.0), label="Control")
    plate["a"].plot(x, np.exp(-x / 6.0), label="Treated")
    plate["a"].set_xlabel("Time (h)")
    plate["a"].set_ylabel(r"Normalized signal ($\mu\mathrm{M}$)")
    mint.direct_labels(plate["a"])
    # Plot into plate["b"], plate["c"], plate["d"] ...
    plate.label_panels()
    return plate
```

---

## CLI & Agent Skill

```bash
# Chat figures from JSON or an embedded-spec PNG
mintfig explain spec.json --out fig.png --write-spec
mintfig explain fig.png --style dark --palette okabe_ito --out fig_dark.png
mintfig explain --show-spec fig.png

# Publication scripts: execute, preflight (14 rules), and export reproducible bundle
mintfig run plot.py --journal nature --bundle out/ --json
mintfig run plot.py --journal science --width full --bundle out_sci/ --strict

# Audit existing PDFs & inspect specs
mintfig check figure2.pdf --journal nature --json
mintfig specs --journal nature --json

# Install bundled agent skill (Claude Code, Antigravity, Cursor, Codex, AGENTS.md, CLAUDE.md)
mintfig skill --install
mintfig skill --install --target claude,antigravity,cursor,codex,agents-md,claude-md --root .
```

Exit codes: `0` clean pass · `1` error-level issue (or warning under `--strict`) · `2` invalid spec, script contract violation, or runtime error.

---

## Benchmarks & Development

- **Chat figure benchmark (`evals/figure_bench/`)**: timed end-to-end benchmark of fresh agents reading only `SKILL.md` across 10 core tasks and 5 held-out tasks with an independent drawn-text layout audit ([evals/figure_bench/README.md](https://github.com/blaiszik/mintfig/blob/main/evals/figure_bench/README.md)).
- **Publication repair eval (`evals/`)**: 10 clean control scripts and 25 messy agent-written scripts testing `mintfig run --json` + `fix_hint` repair loops ([evals/eval_report.md](https://github.com/blaiszik/mintfig/blob/main/evals/eval_report.md)).

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
```
