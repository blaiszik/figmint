# mintfig

**Give your coding agent visual taste — and a fact-checker.**

Working with Claude Code, Codex, Cursor, or Antigravity shouldn't end in 16 numbers buried in prose or a cramped default Matplotlib chart with tiny text, truncated axes, and unnamed error bars. `mintfig` upgrades your agentic coding interface into a visual briefing loop: agents turn raw results into beautiful, publication-grade graphics whose headlines are checked against the plotted data — or automatically audit and upgrade the Matplotlib you already write (`mint.check`, `mint.style`, `mintfig hook --install`).

In [figure-bench](evals/figure_bench/README.md), agents writing default Matplotlib shipped a layout or text defect in **13 of 15** figures and put the right number in the headline in only **4 of 15**. Watch the exact same 5-seed ablation reply move from a text wall, to default agent Matplotlib, to `mintfig`:

![Comparison of an agent's text-only reply, default agent Matplotlib (ship: false), and mintfig reply (ship: true)](gallery/output/readme_comparison/opener.gif)

<details>
<summary>Inspect all three replies as static frames</summary>

1. **Agent text-only:**
   > I ran the ablation with five variants and five seeds each. The full model reaches 0.82 test accuracy (95% CI 0.80–0.84). Removing augmentation gives 0.80 (0.78–0.82) and a smaller encoder 0.78 (0.75–0.81), both within seed noise of the full model. Removing retrieval drops accuracy to 0.74 (0.71–0.77), a loss of 8 points, and removing fine-tuning drops it to 0.69 (0.66–0.72), a loss of 13 points; neither interval overlaps the full model's. On the validation curves the three main variants start together, but by step 500 the full model is at 0.66, no retrieval at 0.60 and no fine-tuning at 0.48, and the order holds through step 2,000, where they end at 0.82, 0.74 and 0.68.

2. **Default agent Matplotlib (`mint.check` → `ship: false`):** text shrinks to **8.1 px** at 700 px chat width, bar axis starts at 0.55 (`bar_baseline_nonzero`), error bars and bands are unlabelled (`interval_unlabelled`), rotated labels crowd, boxed legend, and a topic-only title ("Ablation Results") with no takeaway number.

   ![Default agent Matplotlib render of the ablation](gallery/output/readme_comparison/matplotlib_default.png)

3. **`mintfig` reply (`mint.check` → `ship: true`):** *"Retrieval and fine-tuning are the two components worth keeping; the other two are within seed noise."*

   ![Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13](gallery/output/readme_comparison/mintfig_reply.png)

   *No retrieval 0.74 and no fine-tuning 0.69 against 0.82 for the full model; neither 95% CI (5 seeds) overlaps it.*

</details>

Reproduced from the exact same data by [`gallery/make_readme_comparison.py`](gallery/make_readme_comparison.py). The reply is one sentence, the figure, and one caption; `fig.save()` hands the agent the image line and caption in `summary["deliver"]` ([Put it in front of the reader](#put-it-in-front-of-the-reader)).

### Three steps to adopt

1. **Check the Matplotlib you already have (`mint.check`, `mintfig check plot.py` / `analysis.ipynb`) — zero rewrite.** One call reads plotted values back from bars, lines, scatter, heatmaps, histograms, CI bands, and boxplots, verifies every number in your title or claim against the data, and measures text at reading width (`chat`, `narrow`, `slide`).
2. **Add an automatic agent guardrail (`mintfig hook --install`, `mintfig skill --install --global`).** Install the skill globally for Claude Code, Codex, Cursor, and Antigravity, and wire a silent `PostToolUse` hook that checks agent-written Matplotlib scripts automatically and only speaks up when a figure fails `ship`.
3. **Explain results in one call (`mint.explain`, `mintfig plot`) & ship journal plates (`mint.Plate`, `mintfig run`).** Lead with a takeaway sentence and compose panels by question with direct labels, named uncertainty, colorblind-safe themes, HTML/terminal delivery, and exact-mm submission bundles for *Nature*, *Science*, *Cell*, PNAS, and NeurIPS.

[Quickstart](#quickstart) · [Check Existing Matplotlib](#already-have-matplotlib-check-it-mintcheck) · [Explain Results](#explain-a-result-mintexplain) · [Forms at a Glance](#pick-the-form-by-the-question) · [Themes & Palettes](#themes--palettes) · **[Full Visual Gallery](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md)** · [Publication Plates](#publication-figures) · [CLI & Agent Skill](#cli--agent-skill)

---

![Dose-response figure: triplicate wells on a log dose axis, one colour per compound across panels](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_science/dose_response.png)

---

## Quickstart

```bash
pip install mintfig
# or with uv
uv add mintfig
# or zero-install check on any existing plotting script
uvx mintfig check plot.py
```

Give your coding agents the bundled skill globally (auto-detects Claude Code, Codex, Cursor, Antigravity) and enable the automatic Matplotlib audit hook:

```bash
mintfig skill --install --global
mintfig hook --install
```

### Already have Matplotlib? Check it (`mint.check`)

Most figures an agent ships are plain Matplotlib, and in [figure-bench](evals/figure_bench/README.md) agents writing it without guardrails shipped a layout or text defect in 13 of 15 figures and stated the correct number in the headline in only 4 of 15. `mint.check` audits any Matplotlib or Seaborn figure without rewriting it:

```python
import matplotlib.pyplot as plt
import mintfig as mint

fig, ax = plt.subplots(figsize=(12, 5))
ax.bar(["full model", "no retrieval", "no fine-tuning"], [0.82, 0.74, 0.69], yerr=[0.02, 0.03, 0.03])
ax.set_ylim(0.6, 0.85)
ax.set_title("Removing retrieval costs 12 points of accuracy")

report = mint.check(fig, dpi=150)   # or mint.check(fig, "the sentence you will send")
print(report)
```

```text
{
  "ship": false,
  "claim": "Removing retrieval costs 12 points of accuracy",
  "numbers": ["12 points: NOT FOUND in the data; closest: full model vs no retrieval: 0.82 − 0.74 = 8 points"],
  "issues": [
    "bar_baseline_nonzero: Bars start at zero but the value axis runs 0.6–0.85, so bar lengths overstate the differences.",
    "claim_number_mismatch: The claim states '12 points', which matches no value, difference, ratio, ...",
    "text_too_small: 10 text(s) under 11 px as read: 'full model' 8.1 px, ... The 1800 px PNG is shown 700 px wide, ...",
    "interval_unlabelled: The figure draws error bars or bands but never says what they are.",
    "axis_unlabelled: Axes 0 has numbers on its y axis but no label saying what they measure."
  ],
  "facts": [
    "highest full model 0.82, 0.08 above no retrieval (0.74), 1.11×; lowest no fine-tuning 0.69",
    "intervals of full model (0.8–0.84) and no retrieval (0.71–0.77) do not overlap"
  ],
  "display": {"png_px": [1800, 750], "shown_px": [700, 292], "min_text_px": 8.1}
}
```

(Abridged. Each entry in `report["issues"]` also carries a `fix_hint`, here "figsize width ≈ 4.7 in at dpi=150 … or set text to at least 14 pt".)

- **The claim, against the data.** Bars, lines, error bars, scatter points, heatmaps (`QuadMesh`), histograms, `fill_between` CI bands, boxplots, and images are read back from the drawn artists. Each number the headline (or `claim=`) states is checked against values, differences, ratios, percentage changes, shares, and crossings (ignoring model IDs like `Llama-3.1`/`8B` and sample counts like `5 seeds`).
- **At reading size.** Text is measured after scaling the PNG to `width="chat"` (700 px), `"narrow"` (450 px, phones), or `"slide"` (1280 px), alongside overlaps, text struck by lines, malformed text, clipping, truncated bar baselines, and rainbow colormaps.
- **Zero-rewrite CLI, notebooks, and hooks.** Run `mintfig check plot.py` (auto-detects your project `.venv`, or pass `--python /path/to/python`), `mintfig check analysis.ipynb` (zero extra deps), `%load_ext mintfig` in Jupyter/marimo, or `mintfig hook --install` so agent-written Matplotlib scripts are checked automatically with exit `0` (ship), `1` (fix first), or `2` (script error).
- **Upgrade existing Matplotlib in 1–2 lines (`mint.style()`, `mint.explain(takeaway, fig)`).** Wrap existing plotting code in `with mint.style(width="chat"):` for chat-readable sizing, despining, and CVD-safe palettes without leaking global `rcParams`, or pass any existing Matplotlib/Seaborn `Figure` or `Axes` straight into `mint.explain(takeaway, fig)` to get the takeaway frame, `mint.check` facts, interactive HTML, and `deliver` ([gallery/byo_matplotlib_examples.py](gallery/byo_matplotlib_examples.py)).

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

No Python script needed? Render directly from CSV or JSON/stdin:

```bash
mintfig plot data.csv --kind auto --takeaway "Checkout p99 is 4x slower" --out fig.png
mintfig explain --example | mintfig explain - --style editorial --palette okabe_ito --out fig.png
```

### Put it in front of the reader

A figure only helps once it is in the reply. `summary["deliver"]` says how: `markdown` (the image line), `caption` (one sentence taken from the facts that back the takeaway), `text` (a plain rendering for a code block where images do not show), and `html` (once saved as `.html`).

```python
summary = fig.save("ablation.png")
deliver = summary["deliver"]
reply = f"Retrieval and fine-tuning both matter.\n\n{deliver['markdown']}\n\n*{deliver['caption']}*"
fig.show()                 # notebook: rich display; Kitty, iTerm2, WezTerm, Ghostty: inline PNG; else text
text = fig.to_text()       # plain text, at most 72 columns, for a code block
fig.save("ablation.html")  # one self-contained page
```

`mintfig doctor` reports which of these work where it runs (inline-image protocol, resolved font, notebook) and renders a sample. The HTML page embeds the figure laid out for 360 px, 450 px, and its own width and picks one with a container query, so text stays at 11 px or more; it follows the reader's light or dark setting; hovering or focusing a mark shows its value, interval, and n, and clicking copies a citation (`ablation.png · b · no retrieval @ 500 = 0.52`) to paste back to the agent. Under the figure there is one quiet line: `data · svg · spec`.

### Words on the marks, tables with graphics, briefings

Entity names in the takeaway and panel titles are drawn in their colour (`color_names=False` turns it off). When the takeaway states a difference between two marks, `compare` draws it as a bracket with the number (`show_delta="auto"`, the default). `density="compact"` gives thinner bars and tighter rows at the same type sizes.

```python
fig = mint.explain(
    "Beta scores 8 points below Alpha; Gamma 13 below",
    mint.compare({"Alpha": 82.0, "Beta": 74.0, "Gamma": 69.0}, label="Accuracy", unit="%",
                 baseline="Alpha", highlight=["Beta", "Gamma"], title="Test accuracy"),
    density="compact",  # thinner bars, tighter rows and gaps; same type sizes
)
```

`mint.table` draws a bar, whisker, or sparkline in the cell beside each number, on one scale per column, so a scorecard no longer needs a bar panel beside it:

```python
rows = [
    {"Model": "full model", "Accuracy": 82.0, "lo": 80.5, "hi": 83.4, "Latency": 182},
    {"Model": "no retrieval", "Accuracy": 74.0, "lo": 72.1, "hi": 75.8, "Latency": 95},
    {"Model": "no fine-tuning", "Accuracy": 69.0, "lo": 67.0, "hi": 71.1, "Latency": 180},
]
scorecard = mint.table(
    rows, units={"Accuracy": "%", "Latency": "ms"}, baseline="full model", highlight="no retrieval",
    interval={"Accuracy": ("lo", "hi")}, interval_label="95% CI, 5 seeds",  # whisker beside the number
    bars="Latency",                                                         # bar from zero, one scale
    spark={"Training": {"full model": [2, 61, 78, 82], "no retrieval": [2, 48, 68, 74],
                        "no fine-tuning": [1, 40, 60, 69]}},                # sparklines, one y range
    title="Accuracy, latency and training curve per variant",
)
table_fig = mint.explain("Dropping retrieval halves latency and costs 8 points of accuracy",
                         scorecard, source="ablation runs")
```

`mint.brief` reads its arguments in order: strings are paragraphs (`"## ..."` starts a section), everything else is a figure. The page opens with a row of thumbnails, one per finding; each finding is its figure with one caption, and in HTML the facts sit in a collapsed "Numbers behind this figure" block.

```python
report = mint.brief(
    "Ablation study",
    "We removed one component at a time and retrained with five seeds.",
    fig,
    "Retrieval is also the slowest component.",
    table_fig,
)
report.save("ablation_brief.html")  # or .md: Markdown with one PNG per figure
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
- **Facts & one-shot shipping (`summary["ship"]`, `mint.lenient()`).** `fig.save()` returns computed `facts` per panel plus a `"ship"` verdict that separates real visual defects from minor advisory warnings so agents don't burn extra turns re-rendering good-enough figures. Advisories include `low_density` (a figure taller than 320 px for fewer than eight values: use `density="compact"`, `mint.table`, or one sentence) and `scales_differ` (two panels with the same label and unit on different ranges); `print(summary)` shows a compact view, `json.dumps(summary)` the full one. For rapid ad-hoc charts, `with mint.lenient():` / `mint.explain(..., strict=False)` / `mintfig explain --lenient` auto-adjusts soft limits (auto-faceting >4 series, auto-stacking cramped panels, trimming oversized lists) instead of rejecting.
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
| Names in the title take their mark's colour; a stated difference is drawn as a bracket | Integrating words and images (Tufte, *Beautiful Evidence* 2006); readers see what they are cued to compare (Franconeri et al., *Psychological Science in the Public Interest* 2021) |
| Numbers in a table carry in-cell bars, whiskers or sparklines on one scale per column | Sparklines and table-graphics (Tufte, *Beautiful Evidence*); bullet graphs (Few, *Information Dashboard Design* 2006) |
| A tall figure with few values is flagged (`low_density`); `density="compact"` tightens it | Data-ink and the shrink principle (Tufte 1983); density (Few 2006) |
| Panels that share a label and unit share a scale, or `scales_differ` says so | Common scales (Cleveland, *The Elements of Graphing Data* 1985); small multiples (Tufte 1983) |
| The text fallback never draws a bar for an interval, and gives no percent change from a near-zero start | Lie factor (Tufte 1983) |
| The HTML page shows values on hover; a briefing opens with one thumbnail per finding, then figures with prose between | Overview first, details on demand (Shneiderman 1996); annotated-chart narrative (Segel & Heer, *IEEE TVCG* 2010); eyes beat memory (Munzner, *Visualization Analysis and Design* 2014) |

---

## Publication Figures

Default Matplotlib figures break journal specifications in subtle ways: 6.4" canvases shrink text below 5 pt when scaled to an 89 mm column, `bbox_inches="tight"` mutates PDF MediaBox dimensions, Type 3 fonts break Illustrator editing, Computer Modern serif math clashes with Helvetica labels, and 50k-point scatters produce sluggish multi-megabyte PDFs.

![Before vs After default Matplotlib on an 89 mm Nature single-column figure](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/before_after_nature.png)

- **Exact physical column widths** — locked PDF MediaBox dimensions with `constrained_layout` and versioned journal spec provenance.
- **Uniform sans-serif typography & math** — Helvetica/Arial/Liberation Sans/DejaVu Sans for body text and mathtext, Type 42 PDF embedding (`pdf.fonttype = 42`), editable SVG text (`svg.fonttype = "none"`).
- **Multi-panel `Plate` engine & Tufte primitives** — aligned bold panel labels (`a, b, c` / `A, B, C`), auto-stacked `sig_bracket`, `scalebar`, `direct_labels`, `zoom_inset`, `range_frame`, `ghost_context`, `tufte_boxplot`, `slopegraph`, and `sparkline`.
- **Hybrid vector/raster & byte-reproducible bundles** — `mint.pub.save_figure(..., rasterize_above=10_000)` keeps axes crisp vector while rasterizing dense scatter/mesh layers; `mintfig run --bundle out/` emits `figure.pdf`, `figure.svg`, `preview.png`, `proof.png` (CVD + grayscale scorecard), `figure.tex`, `figure.json`, `reproduce.py`, and `report.json`.

`mint.Plate` and `mint.figure` stay at the top level; every other publication tool (styling, annotation primitives, journal specs, export, preflight, palettes) lives in `mint.pub`. PDF checks (`mint.pub.preflight_pdf`, `mintfig check`, `mintfig run --bundle`) read PDFs with `pypdf`: `pip install "mintfig[pub]"`.

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
    mint.pub.direct_labels(plate["a"])
    # Plot into plate["b"], plate["c"], plate["d"] ...
    plate.label_panels()
    return plate
```

---

## CLI & Agent Skill

```bash
# Check any Matplotlib script, notebook, or PDF against its data at reading size (exit 0 ship / 1 fix / 2 error)
mintfig check plot.py --claim "Removing retrieval costs 8 points" --width chat --json
mintfig check plot.py --python .venv/bin/python   # auto-detects project .venv when omitted
mintfig check analysis.ipynb --width chat --json
mintfig check figure2.pdf --journal nature --json

# Install bundled agent skill globally (or per project) & wire automatic PostToolUse hooks
mintfig skill --install --global                  # auto-detects ~/.claude, ~/.codex, ~/.gemini, ~/.cursor
mintfig skill --install --target all --root .
mintfig skill --print --all                       # print SKILL.md + all references/*.md
mintfig hook --install                            # auto-audit agent Matplotlib writes (silent on pass)
mintfig hook --status

# Zero-script: plot CSV/JSON or SWE tool outputs (hyperfine, pytest-benchmark, go/cargo bench, CI timings, k6, esbuild)
mintfig plot data.csv --kind auto --takeaway "..." --density compact --out fig.png
mintfig plot hyperfine.json --kind auto --text               # <=72-col Unicode terminal summary (no PNG)
mintfig plot bench.json --kind auto --markdown               # GitHub-flavored Markdown summary
mintfig diff main_bench.json pr_bench.json --markdown --fail-on-regression 5
mintfig edit fig.png --drop "no augmentation" --no-color-names --out fig2.png

# Chat figures from JSON or an embedded-spec PNG
mintfig explain spec.json --out fig.png --write-spec
mintfig explain fig.png --style dark --palette okabe_ito --out fig_dark.png
mintfig explain --show-spec fig.png
mintfig doctor                                    # which delivery surfaces work here; renders a sample

# Publication scripts: execute, preflight (14 rules), and export reproducible bundle
mintfig run plot.py --journal nature --bundle out/ --json
mintfig run plot.py --journal science --width full --bundle out_sci/ --strict
mintfig specs --journal nature --json
```

Exit codes: `0` clean pass · `1` error-level issue (or warning under `--strict`) · `2` invalid spec, script contract violation, or runtime error.

---

## Upgrading from 0.2

0.3.0 is a breaking release: the top level holds only what an agent calls, and there are no aliases. A moved name raises an `AttributeError` that names its new home.

- Publication helpers (annotation primitives, `save_figure`, preflight, journal specs, `apply` / `use`, palettes and colormaps) → `mint.pub.*`, e.g. `mint.pub.direct_labels`. `mint.Plate` and `mint.figure` stay.
- Themes and explain palettes (`THEMES`, `get_theme`, `EXPLAIN_PALETTES`, ...) → `mint.themes`.
- `audit_figure`, `audit_layout`, `audit_epistemic`, `build_narrative` → `mint.audit` (they already run inside `explain()`).
- `install_skill`, `get_skill_markdown`, `get_agents_snippet` → `mint.skill`; the CLI (`mintfig skill --install`) is unchanged.
- `explain_from_spec(spec)` → `mint.load(spec)`; `render_html` / `render_terminal` / `show_in_terminal` → `fig.to_html()`, `fig.to_text()`, `fig.show()`.
- `pypdf` is an extra: `pip install "mintfig[pub]"` for PDF checks.

---

## Benchmarks & Development

- **Chat figure benchmark (`evals/figure_bench/`)**: timed end-to-end benchmark of fresh agents reading only `SKILL.md` across 10 core tasks and 5 held-out tasks with an independent drawn-text layout audit, plain-Matplotlib baseline arms, and a delivery check on the agent's reply ([evals/figure_bench/README.md](https://github.com/blaiszik/mintfig/blob/main/evals/figure_bench/README.md)). Whether readers do better with the figure reply than with text has not been measured yet.
- **Skill trigger evaluation (`evals/trigger_eval/`)**: 40 realistic developer and scientist prompts (20 positive, 20 negative, zero mentions of `mintfig`) testing skill recall (>= 85%) and false-trigger rate (<= 5%) with both a deterministic offline rubric and a `--live` CLI adapter ([evals/trigger_eval/README.md](evals/trigger_eval/README.md)).
- **Publication repair eval (`evals/`)**: 10 clean control scripts and 25 messy agent-written scripts testing `mintfig run --json` + `fix_hint` repair loops ([evals/eval_report.md](https://github.com/blaiszik/mintfig/blob/main/evals/eval_report.md)).

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
```
