# mintfig

**Give your coding agent visual taste — and a fact-checker.**

`mintfig` turns Claude Code, Codex, Cursor, Gemini CLI, and Antigravity into a verified visual briefing loop: publication-grade editorial graphics, high-res **2×4 dot-matrix terminal charts** (`--matrix`) for terminals and SSH, and automatic legibility + fact audits for any Matplotlib code an agent already writes.

[Quickstart](#quickstart) · [Audit Matplotlib (`mint.check`)](#audit-existing-matplotlib-mintcheck) · [Terminal Matrix](#terminal-matrix--24-bit-true-color) · [Forms](#pick-the-form-by-the-question) · **[Benchmark](#measured-on-figure-bench-v01)** · [Themes](#themes--palettes) · [Publication Plates](#publication-figures) · **[Full Gallery →](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md)**

![Three-panel checkout latency canary combining log-scale ECDF, deterministic beeswarm raw traces, and a clean booktabs table-graphics scorecard](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/readme_comparison/repo_header_hero.png)

*Generated in one `mint.explain(..., style="prism", density="compact", width="slide")` call (`ship: true`, 0 issues): log-scale ECDF with labeled `p50`/`p95` guides, deterministic beeswarm with tabular medians, and a clean booktabs `mint.table` scorecard with CI whiskers, latency bars, and 7-day rollout sparklines ([generator](https://github.com/blaiszik/mintfig/blob/main/gallery/make_repo_header.py)).*

---

## Quickstart

```bash
pip install mintfig                    # core library + CLI + MCP server
pip install "mintfig[chip]"            # + inline micro-graphics (mintchip)
uvx mintfig demo                       # 15-second zero-install terminal showcase
uvx mintfig check plot.py              # audit any existing Matplotlib script (zero rewrite)
```

Wire `mintfig` into your coding agent (skills, automatic Matplotlib audit hooks, and the zero-dep MCP server with interactive `ui://mintfig/figure` MCP App views):

```bash
mintfig skill --install --global       # Claude Code, Codex, Cursor, Gemini CLI, Antigravity, Copilot
mintfig hook --install --global        # auto-audit Matplotlib scripts (Claude Code & Cursor)
mintfig mcp --install                  # register stdio MCP server across detected harnesses
# Or wire directly via your harness CLI:
claude mcp add mintfig -- uvx mintfig mcp
gemini extensions install https://github.com/blaiszik/mintfig
```

Watch an agent's wall of 32 numbers turn into inline [`mintchip`](https://github.com/blaiszik/mintchip) sparklines, a forest-plot table, and an interactive `mintfig` figure you can hover and click to cite back:

![Wall of 32 agent numbers transformed into mintchip inline chips, a forest-plot table, and an interactive mintfig figure](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/readme_comparison/opener.gif)

<details>
<summary>Compare text-only vs default Matplotlib vs mintfig on the same 5-seed ablation</summary>

1. **Default Matplotlib (`mint.check` → `ship: false`):** text shrinks to **8.1 px** at 700 px chat width, bar axis starts at 0.55 (`bar_baseline_nonzero`), unnamed error bars, and topic-only title.
   ![Default agent Matplotlib render of the ablation](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/readme_comparison/matplotlib_default.png)
2. **`mintfig` reply (`ship: true`):** *"Retrieval and fine-tuning are the two components worth keeping; the other two are within seed noise."*
   ![Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/readme_comparison/mintfig_reply.png)

</details>

---

## Audit existing Matplotlib (`mint.check`)

Without guardrails, only **35%** of agent-written Matplotlib charts pass legibility and layout checks on [figure-bench v0.1](https://github.com/blaiszik/mintfig/blob/main/docs/figure-bench.md). Adding `mint.check` lifts plain Matplotlib to **91%** with zero library rewrite.

![mintfig check auditing a broken Matplotlib figure, catching a wrong headline claim and unreadable text, and verifying the fix](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/readme_comparison/mintcheck.gif)

```python
import mintfig as mint

report = mint.check(fig, "Removing retrieval costs 12 points of accuracy", dpi=150)
print(report)  # ship: false -> flags "12 points" (data shows 8), truncated bar axis, 8.1 px text + fix_hint
```

- **Checks claims against drawn artists** (bars, lines, error bars, scatter, heatmaps, histograms, bands, boxplots) and measures true pixel legibility at `width="chat"` (700 px), `"narrow"` (450 px), or `"slide"` (1280 px).
- **Zero-rewrite CLI & hooks:** run `mintfig check plot.py`, `mintfig check analysis.ipynb`, `%load_ext mintfig`, or `mintfig hook --install --global` (exit `0` ship · `1` fix · `2` error).
- **1-line upgrade:** wrap existing code in `with mint.style(width="chat"):` or pass any Matplotlib/Seaborn `Figure`/`Axes` into `mint.explain(takeaway, fig)`.

---

## Terminal Matrix & 24-bit True-Color

Over SSH, inside `tmux`, or in a text-only coding agent? Pass `--matrix` (or `mode="matrix"`; alias `--braille`) for high-resolution **2×4 Unicode dot-matrix** charts (using the 2×4 Braille dot-pattern block + **24-bit ANSI true-color**) with shaded CI ribbons, wide multi-panel views (`width >= 104`), true-color heatmaps, box-drawn PR KPI cards, and `mintchip` tables:

![Animated Remotion showcase of mintfig 2x4 dot-matrix terminal charts, 24-bit true-color matrices, PR KPI cards, and mintchip tables](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/terminal/braille_showcase.gif)

```bash
mintfig plot training_runs.csv --matrix --style obsidian    # 2×4 dot-matrix trend + shaded 95% CI ribbons
mintfig watch train_metrics.csv --matrix --width auto       # live-reloading terminal chart on file change
mintfig card pr418_card.json --terminal --style obsidian    # rounded KPI tiles + inline sparklines + panel
```

**[See all 8 Terminal Matrix & True-Color examples, snippets & raw ANSI captures →](https://github.com/blaiszik/mintfig/blob/main/docs/terminal-braille.md)** · **[Remotion Video Source](https://github.com/blaiszik/mintfig/tree/main/promo/demo-video)**

---

## Explain a result (`mint.explain`)

State the conclusion first, pick each panel by the question it answers, and check `summary["ship"]` and `summary["panels"][i]["facts"]` before sending:

```python
import mintfig as mint

fig = mint.explain(
    "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
    mint.compare(
        {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
        error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77), "no fine-tuning": (0.66, 0.72)},
        error_label="95% CI, 5 seeds",
        title="Both losses are outside seed noise", label="Test accuracy",
        highlight=["no retrieval", "no fine-tuning"],
    ),
    mint.trend(
        [0, 500, 1000, 1500, 2000],
        {"full model": [0.02, 0.61, 0.76, 0.80, 0.82],
         "no retrieval": [0.02, 0.52, 0.67, 0.72, 0.74],
         "no fine-tuning": [0.01, 0.44, 0.60, 0.66, 0.69]},
        title="The gap opens in the first 500 steps", label="Validation accuracy", x_label="Training step",
    ),
    kicker="ABLATION STUDY",
    source="runs/ablation_2026-11 (5 seeds per variant)",
    style="editorial",
)
summary = fig.save("ablation.png")  # facts, ship verdict, alt_text, and deliver (markdown/caption/text/html)
fig.save("ablation.html")           # adaptive light/dark SVG with hover values & click-to-cite
```

- **Zero-script CLI:** `mintfig plot data.csv --kind auto --takeaway "..." --out fig.png` (supports CSV/TSV/JSON, `hyperfine`, `pytest-benchmark`, `go`/`cargo bench`, JUnit).
- **Multi-surface delivery:** `fig.show()` auto-detects notebooks, Kitty/iTerm2/WezTerm/Ghostty (with `tmux` passthrough), or Braille/plain text (`mintfig doctor` inspects your environment).
- **Briefings & round-tripping:** combine prose and figures with `mint.brief(...)`, pin hues across turns with `mint.Session`, and revise any saved PNG directly with `mint.edit("fig.png", ...)`.

---

## Pick the form by the question

Every form enforces zero baselines, direct labels, horizontal text, named uncertainty, and automatic `facts`. **[Browse all 45+ rendered examples with code in the Gallery →](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md)**

| Form | Question & key encodings | Example |
| :--- | :--- | :---: |
| **`mint.compare`** | **Size & intervals:** sorted bars from zero, dots + whiskers (`error=`, `inner_error=`), `n=`, `baseline=`, auto delta brackets (`show_delta="auto"`). | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/compare_intervals.png" width="360" alt="mint.compare with 95% CIs and baseline"> |
| **`mint.trend`** | **Change over time, dose, or scale:** direct end labels, ISO dates, `events=`, `band=`, raw `points=`, `fit=`, `log=`/`log_x=`, `facet=True`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/trend_dates_events.png" width="360" alt="mint.trend with ISO dates and events"> |
| **`mint.change`** | **Before → after:** paired slopegraph with inline deltas. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain/benchmark_gains.png" width="360" alt="mint.change paired slopegraph"> |
| **`mint.distribution`** | **Raw observations & tails:** dot strips, deterministic **beeswarm (`mode="swarm"`)**, **quantile dotplots (`mode="quantile"`)**, and **ECDFs (`mode="ecdf"`)** with tabular readouts. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/distribution_swarm.png" width="360" alt="mint.distribution beeswarm with tabular median column"> |
| **`mint.histogram`** | **Binned shape / modality:** single or stacked shared-axis histograms with median and `% above reference` facts. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/histogram_bimodal.png" width="360" alt="mint.histogram bimodal latency distribution"> |
| **`mint.relate`** | **Two continuous measures:** grouped scatter, `fit=True` OLS + 95% slope CIs, `frontier=True` Pareto hull, `regions=`, `callouts=`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/relate_groups_fit.png" width="360" alt="mint.relate grouped scatter with linear fits"> |
| **`mint.share`** | **Part of a whole:** sorted percentage bars (folding tails past `top=` into `"Other (n)"`). | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain/build_time.png" width="360" alt="mint.share build time breakdown"> |
| **`mint.matrix`** | **Two categorical axes:** annotated heatmaps, `diverging=True`, `normalize="row"|"col"` + `show_counts=True` confusion matrices, `triangle="lower"|"upper"`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_workflows/05_corr_matrix_triangle.png" width="360" alt="mint.matrix lower-triangle correlation matrix"> |
| **`mint.forest`** | **Effect sizes & meta-analysis:** `sqrt(n)` markers, CI whiskers vs null line, pooled summary diamond, aligned `est [lo, hi]` + `n` columns. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/forest_ab_meta.png" width="360" alt="mint.forest effect-size plot with pooled diamond"> |
| **`mint.table`** | **Lookups & table graphics:** booktabs scorecards with in-cell **`bars=`**, **`interval=`** whiskers, **`spark=`** sparklines, `bold_best=`, and `.to_markdown()`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_forms/table_graphics_scorecard.png" width="360" alt="mint.table scorecard with in-cell CI whiskers, bars, and sparklines"> |
| **`mint.card`** | **PR & release KPI cards:** bold metric tiles, deltas, and sparklines above a companion panel; exports light/dark `<picture>` pairs or `--terminal`. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_release/pr_card_light.png" width="360" alt="mint.card PR KPI summary card"> |
| **`mint.waterfall` / `timeline` / `flow`** | **Agent workflow forms:** attribution delta bridges, parallel execution span traces, and cohort attrition funnels. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_workflows/01_ablation_waterfall.png" width="360" alt="mint.waterfall ablation attribution bridge"> |
| **`mint.explain`** | **Multi-panel arguments:** 2–4 panels sharing one colour per entity, words-on-marks headlines, and embedded PNG spec round-tripping. | <img src="https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain/checkout_story.png" width="360" alt="mint.explain four-panel regression story"> |

---

## Measured on `figure-bench v0.1`

Across 100 tasks (400 fresh Claude Sonnet 5.5 runs), `mintfig` ships **100%** defect-free figures (**98.0** composite) in **11.7 s** median — vs **91%** for plain Matplotlib + `mint.check`, **54%** for prompt-coached Matplotlib, and **35%** for default Matplotlib.

![Across 100 tasks, mintfig ships 100% defect-free figures (98.0) in 11.7 s vs 54% coached and 35% default Matplotlib](https://raw.githubusercontent.com/blaiszik/mintfig/main/docs/assets/figure_bench/arms_overview.png)

**[Full 4-arm report & failure anatomy →](https://github.com/blaiszik/mintfig/blob/main/docs/figure-bench.md)** · [Benchmark spec](https://github.com/blaiszik/mintfig/blob/main/evals/figure_bench/README.md) · [Wild-50 `mint.check` audit](https://github.com/blaiszik/mintfig/blob/main/evals/check_audit/README.md)

---

## Themes & Palettes

Mix any of **15 surface themes (`style=`)** — flagship curated editions `prism` (`npg`), `folio`, `nordic`, `obsidian`, `monograph` (`ivory`), plus `mintfig`, `mint`, `pine` (`mint_dark`), `botanical`, `editorial`, `paper`, `bold`, `dark`, `mono`, `sketch` — with **11 CVD- & grayscale-verified palettes (`palette=`)**: `mint`, `spearmint`, `matcha`, `glacier`, `mineral` (zero-yellow), plus `default`, `okabe_ito`, `tol`, `earth`, `ocean`, `berry`. Set repo defaults via `MINTFIG_STYLE` or `[tool.mintfig]` in `pyproject.toml`.

![mintfig color palettes, surface themes, and editorial colormaps](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/explain_themes/palettes_overview.png)

| `style="folio"` (editorial serif) | `style="nordic"` (whisper-mint) | `style="obsidian"` (dark mode) |
| :---: | :---: | :---: |
| ![folio theme](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/palette_matching/npg_editorial_serif.png) | ![nordic theme](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/palette_matching/nordic_emerald_slate.png) | ![obsidian dark theme](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/palette_matching/pine_obsidian_dark.png) |

**[View all 15 themes & 11 palettes side-by-side →](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#themes--color-palettes)**

---

## Publication Figures

Lock exact journal millimetre widths (`nature`, `science`, `science_advances`, `cell`, `pnas`, `neurips`), Type 42 sans-serif PDF/SVG output with Illustrator `gid=` layers, CMYK gamut preflight, auto-drafted captions, and CVD proof sheets (`pip install "mintfig[pub]"`). Convert any `mint.explain` directly with `mint.pub.to_publication(fig, journal="nature")` or build multi-panel plates with `mint.Plate(...)`.

![Before vs After default Matplotlib on an 89 mm Nature single-column figure](https://raw.githubusercontent.com/blaiszik/mintfig/main/gallery/output/before_after_nature.png)

| Target | Width Presets (mm) | Body / Tick / Panel | Panel Case | Combo / Line DPI |
| :--- | :--- | :---: | :---: | :---: |
| **Nature** (`nature`) | `single`: 89 · `mid`: 120 · `double`: 183 | 6.5 / 6.0 / 8.0 pt | `a, b, c` | 500 / 1000 |
| **Science** (`science`) | `single`: 55 · `double`: 120 · `full`: 184 | 7.0 / 6.0 / 8.5 pt | `A, B, C` | 600 / 1200 |
| **Cell** (`cell`) | `single`: 85 · `mid`: 114 · `double`: 174 | 7.0 / 6.0 / 8.5 pt | `A, B, C` | 500 / 1000 |
| **PNAS** (`pnas`) | `single`: 87 · `mid`: 114 · `double`: 178 | 7.0 / 6.5 / 9.0 pt | `A, B, C` | 600 / 1200 |
| **NeurIPS** (`neurips`) | `single`: 67 · `mid`: 111.8 · `double`: 139.7 | 7.5 / 6.5 / 8.5 pt | `a, b, c` | 500 / 1000 |

**[View Nature, Science, Cell & NeurIPS publication plates →](https://github.com/blaiszik/mintfig/blob/main/gallery/README.md#publication-figures-mintfigure-mintplate-mintfig-run)**

---

## CLI Cheat Sheet

```bash
# Audit & zero-rewrite hooks
mintfig check plot.py --claim "..." --width chat --json
mintfig check analysis.ipynb --json
mintfig skill --install --global && mintfig hook --install --global

# Plot, diff, watch & KPI cards (PNG, Markdown, or 2×4 dot-matrix terminal)
mintfig plot data.csv --kind auto --takeaway "..." --out fig.png
mintfig plot data.csv --matrix --style obsidian
mintfig watch train.csv --matrix --style obsidian --width auto
mintfig diff main_bench.json pr_bench.json --matrix
mintfig card spec.json --out card.png --pair            # light/dark <picture> (or --terminal)
mintfig edit fig.png --style folio --out fig2.png

# Showcase, diagnostics, MCP & publication bundles
uvx mintfig demo --html showcase.html
mintfig doctor --json
mintfig mcp --install
mintfig run plot.py --journal nature --bundle out/ --json
```

<details>
<summary>Evidence-based design rules & upgrading from 0.2</summary>

- **Design rules enforced automatically:** assertion–evidence headlines (Alley & Neeley 2005), zero-baseline position/length encodings (Cleveland & McGill 1984), ≤4 series & small multiples (Cowan 2001; Tufte 1983), direct horizontal labels (Mayer), raw dots & named intervals (Weissgerber et al. 2015; Cumming et al. 2007), cross-panel entity colour consistency (Qu & Hullman 2018), CVD/grayscale/WCAG 4.5:1 checks (Machado et al. 2009), ≥11 px display floor, and table-graphics sparklines/whiskers (Tufte 2006; Few 2006).
- **Upgrading from 0.2 → 0.3:** publication helpers moved to `mint.pub.*` (`mint.Plate` and `mint.figure` stay top-level); themes moved to `mint.themes`; audit helpers to `mint.audit`; skill helpers to `mint.skill`; `explain_from_spec` → `mint.load(spec)`; renderers → `fig.to_html()`, `fig.to_text()`, `fig.show()`; PDF checks use `pip install "mintfig[pub]"`.
- **Full argument reference:** [`src/mintfig/assets/SKILL.md`](https://github.com/blaiszik/mintfig/blob/main/src/mintfig/assets/SKILL.md) (verified against the live API on every test run).

</details>

---

## License

MIT — see [LICENSE](https://github.com/blaiszik/mintfig/blob/main/LICENSE).
