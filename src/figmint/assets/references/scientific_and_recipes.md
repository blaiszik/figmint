# figmint Chat Figures: Scientific Details, Sizing & Recipes

Read this reference when building complex multi-panel scientific figures, sizing tight layouts, pinning entity colours across figures, or editing an existing figure spec.

## Scientific data guidance

- **Show uncertainty and name it:**
  | You have | Use |
  | :--- | :--- |
  | Raw replicates per condition (seeds, wells, samples) | `fm.distribution` — every observation drawn (`stat="mean"` if claim is about means), or `mode="quantile", quantiles=20` for countable frequency dotplots (5% per dot) |
  | Raw replicates or units along x (dose, time, step) | `fm.trend(x, points={name: [[reps], ...]})` or tidy `fm.trend("x", "group", y="val", data=rows)` (repeated `(x, group)` rows auto-become `points=`) |
  | Only an estimate and its interval | `fm.compare(error=..., inner_error=..., error_label="50% / 95% CI")` or `fm.trend(band=..., band_label="± 1 s.d.")` |

  An unlabelled interval triggers `interval_unlabelled`. `facts` state whether intervals overlap, exceedance probabilities above `reference=`, and empirical superiority `P(group > baseline)` on `distribution`. Do not write "significant" unless you ran the test, and name it in `note=`; advisory `claim_overstates_uncertainty` and `claim_number_mismatch` warn on clear mismatches.
- **Values spanning decades:** `log=True` for y (`compare`, `trend`, `distribution`), `log_x=True` for x (`trend`, `relate`). Bars are never drawn on a log axis.
- **Lower is better** (loss, error, IC50): `sort="asc"` puts the best item on top (`fm.table(..., sort="cost", bold_best="min")`).
- **Units & Unicode:** `unit=` is a short symbol (`ms`, `%`, `mg/L`, `×`); words go in `label=`. Write Unicode directly (`µm`, `cm⁻³`, `°C`, `Å`, `χ²`); `$...$` triggers `latex_markup`. Write fractional exponents as `"d⁻½"` or `"1/√d"`, never `"d⁻¹ᐟ²"`.
- **x unit:** on numeric `trend` and `relate`, a one-word `(...)` or `[...]` at the end of `x_label` ("Time (h)") is parsed as the x unit in `facts` ("4 h"). Override with `x_unit="steps"` or disable with `x_unit=""`.
- **Numbers:** ~3 significant figures with `×10ⁿ` for extreme magnitudes, never rounded to zero. Override via `fmt=".2f"` or `fmt="{:.1f} ms"`.
- **Missing values:** pass `None` or `NaN`; gaps draw as gaps (`—` in `matrix` and `table`), are counted in `facts`, and belong in `note=`.
- **Small n (<5):** `distribution` shows points + centre mark only; mention `n` in the title or `note=`.
- **>4 ordered levels** (doses, temperatures): `highlight=` the 1–3 the claim is about (rest become labelled grey context) or `facet=True`.
- **Log-axis slopes:** with `trend(log=True)` and numeric x, `facts` report log₁₀(y) slope per x unit with R² (split around interior peaks/troughs); with `log_x=True` too, power-law exponents with 95% CI.

## Height & layout budgets

`too_tall` warns above 135 mm (one screen; at 700 px chat width, 1 mm ≈ 5 px → 675 px). A one-line takeaway plus one full-width panel is approximately:

| Panel | Figure height |
| :--- | :--- |
| `compare` or `share`, N bars | 23 + 5.3·N mm (5 → 50, 10 → 76, 20 → 129) |
| `distribution`, G groups | 33 + 8.5·G mm (4 → 67, 8 → 101) |
| `matrix`, R rows | 28 + 6.3·R mm (6 → 66, 10 → 90, 16 → 128) |
| `table`, R rows | 30 + 5.4·R mm (5 → 57, 10 → 84, 15 → 111) |
| `change`, N items | 60 mm at 4, 71 at 8, 99 at 14 |
| `trend` / `relate` | 79 / 84 mm full width, 66 at half width |

Each extra full-width row adds its height minus ~15 mm; side-by-side panels take the tallest height; `subtitle=` adds 4 mm, `source=` 6 mm, `note=` 4 mm, a second takeaway line 5 mm. Give `matrix`, `table`, and long-label panels a full row via `layout=[["a"], ["b", "c"]]`.

## Colour consistency

A name keeps one colour across every panel of a figure (e.g., `"no retrieval"` stays red across a dot plot, curve, and `fm.table` highlight). `highlight=` assigns red, blue, green, amber in order unless pinned; everything else turns grey; `baseline=` draws in ink. To keep colours across multiple figures in one conversation, pass `colors=summary["colors"]` (or `colors={"no retrieval": "red"}`) to subsequent `fm.explain` calls.

Styles (`style=`): `figmint`, `bold`, `editorial`, `paper`, `dark`, `mono`, `sketch` (illustrative only; warns unless `source=`/`note=` notes illustrative data).
Palettes (`palette=`): `default`, `okabe_ito`, `tol`, `earth`, `ocean`, `berry` (CVD-verified independently of `style=`).

## Recipes (tidy rows & wide DataFrames)

```python
# Row-shaped CSV / JSON records directly (no manual pivoting needed)
fm.compare(rows, name="model", value="score", error=("ci_lo", "ci_hi"), error_label="95% CI", n="n")
fm.trend("step", "variant", y="val_acc", data=rows, x_label="Training step", label="Accuracy")
fm.distribution(rows, group="condition", value="ic50", log=True, label="IC50", unit="µM")
fm.matrix(rows, rows="model", cols="benchmark", value="score", label="Pass rate", unit="%")
fm.relate("cost", "score", data=rows, names="model", groups="family", log_x=True,
          x_label="Cost ($/M tokens)", y_label="Score (%)")

# Exact-lookup scorecard table with mixed units and bold winners
fm.table(
    rows,
    columns=["Model", "GPQA", "SWE-bench", "Cost"],
    units={"GPQA": "%", "SWE-bench": "%", "Cost": "$/M"},
    bold_best={"GPQA": "max", "SWE-bench": "max", "Cost": "min"},
    highlight="New Model",
    baseline="Prev Gen",
    sort="-GPQA",
    title="New Model leads reasoning and coding at half the cost",
)

# Model-release hero cards: grouped benchmarks, extended-thinking boosts, & Pareto frontiers
fm.compare(
    {"GPQA": {"New": 86.4, "Prev": 77.1, "Peer": 83.2}, "SWE": {"New": 74.2, "Prev": 58.6, "Peer": 71.0}},
    highlight="New", baseline="Prev", label="Accuracy", unit="%", title="Head-to-head benchmarks",
)
fm.compare(
    {"New": 76.0, "Prev": 64.0, "Peer": 74.0},
    boost={"New": 10.4, "Prev": 6.2, "Peer": 8.0}, boost_label="Extended thinking",
    highlight="New", baseline="Prev", label="AIME accuracy", unit="%",
)
fm.relate(
    "cost", "score", data=rows, names="model", groups="family", highlight="NewFamily",
    frontier=True, label_all=True, connect_groups=True, log_x=True,
    x_label="Cost ($/M tokens)", y_label="Score (%)", unit="%",
)
# Combine with width="slide", style="paper"|"dark", and accent="#D97757" for wide hero graphics!

# Ratio per item against a reference (dots on log axis around 1)
fm.compare(ratio, log=True, zero=False, reference=(1, "no change"), label="Ratio to reference", unit="×")

# Before/after an event with an untreated control (each unit as % of own pre-event median)
wide = df.pivot(index="time", columns="unit_id", values="value")
rel = wide / df[df.time < t_event].groupby("unit_id").value.median() * 100
fm.trend(rel.index, rel, baseline="untreated", events={t_event: "event"},
         label="Value vs own median before", unit="%")

# Visual-science upgrades: quantile dotplots, nested intervals + inline deltas, callouts & shaded regions
fm.distribution(
    {"treated": treated_samples, "control": control_samples},
    mode="quantile", quantiles=20, baseline="control", reference=(50, "target"),
    highlight="treated", label="Response", unit="%", title="90% of treated runs clear target",
)
fm.compare(
    {"variant A": 84.2, "variant B": 79.1, "control": 74.9},
    error={"variant A": 3.4, "variant B": 3.1, "control": 2.9},
    inner_error={"variant A": 1.6, "variant B": 1.5, "control": 1.4},
    error_label="50% / 95% CI", baseline="control", show_delta=True,
    highlight="variant A", label="Accuracy", unit="%",
)
fm.trend(
    days, {"service": latency}, x_label="Day", label="p99 latency", unit="ms",
    regions=[(10, 14, "migration window")],
    callouts=[(12, 420, "cache cold-start spike")],
)
```

## Harness-adaptive delivery (IDE sidebars, HTML review, & terminals)

- **IDE sidebars (~420–480 px):** pass `width="narrow"` (92 mm, 450 px target width; multi-panel layouts auto-stack vertically so panels stay crisp at ≥12 px text).
- **Interactive HTML review:** `fig.save("review.html")` (or `figmint explain spec.json --out review.html`) emits a zero-CDN self-contained HTML file with embedded SVG, theme-matched surfaces, a toggleable Facts & Data drawer, Download SVG, Copy Spec JSON, and a Critique / Ask Agent feedback panel. Jupyter notebooks render the interactive fragment automatically via `Explanation._repr_html_()`.
- **Terminal delivery:** `figmint show fig.png` (or `spec.json` / `-` with `--mode auto|kitty|iterm2|unicode|ascii`) auto-detects Kitty/Ghostty or iTerm2/WezTerm inline PNG protocols and falls back to crisp Unicode bars, box-drawn tables, and sparklines (`fig.to_terminal()` in Python).
- **Four-level narrative (`summary["narrative"]`):** returns `L1` (construction), `L2` (statistical facts), `L3` (perceptual patterns), `L4` (domain takeaway), and a reader-first `summary` string.

## Editing a returned figure (`fm.edit` & `fm.load`)

```python
# One-line surgical edit on a saved PNG, JSON spec, or Explanation
fm.edit(
    "ablation.png",
    takeaway="Removing fine-tuning costs 13 points of accuracy, retrieval 8",
    highlight="no fine-tuning",
    drop_panel="b",
    style="dark",
    out="ablation_v2.png",
    write_spec=True,
)
# CLI equivalent:
# figmint edit ablation.png --highlight "no fine-tuning" --drop-panel b --style dark --out ablation_v2.png
```

## Attribution bridges (`fm.waterfall`), execution timelines (`fm.timeline`), & zero-script CLI

```python
# Attribution / delta bridge (ablation gains, cost/latency budgets)
fm.waterfall(
    {"+RAG": 8.0, "+Reranker": 3.4, "+CoT": 2.1, "Quantization": -1.5},
    start=("Base model", 69.0),
    total_label="Shipped",
    highlight="+RAG",
    reference=(80.0, "Release target"),
    title="RAG drives 67% of the net gain",
    label="Benchmark accuracy",
    unit="%",
)

# Execution / phase span timeline (CI traces, agent runs, protocols)
fm.timeline(
    [
        ("fetch", 0, 8, "setup"),
        ("compile", 8, 54, "build"),
        ("unit tests", 54, 92, "verify"),
        ("integration", 54, 148, "verify"),
        ("deploy", 148, 160, "release"),
    ],
    highlight="integration",
    reference=(120, "CI SLA"),
    title="Integration tests exceed the 120 s budget",
    x_label="Elapsed (s)",
    unit="s",
)

# Zero-script CLI workflow from a CSV/TSV/JSON/JSONL file:
# figmint inspect results.csv
# figmint plot results.csv --kind auto --takeaway "..." --out fig1.png
# figmint brief fig1.png fig2.png --title "Investigation" --out report.html

# Attrition / cohort / filter funnel with exclusion reasons
fm.flow(
    [
        ("Screened", 1240),
        ("Eligible", 912, "missing baseline"),
        ("Enrolled", 780, "declined consent"),
        ("Completed", 714, "lost to follow-up"),
    ],
    highlight="Eligible",
    title="58% of screened patients complete follow-up",
    label="Cohort size",
    unit="patients",
)

# Fitted scaling curves & clean lower-triangle correlation matrix
fm.trend(compute, {"Dense": loss_d, "MoE": loss_m}, log=True, log_x=True, fit=True,
         x_label="Compute (FLOPs)", label="Validation loss")
fm.matrix(corr, rows=metrics, cols=metrics, diverging=True, center=0.0,
          triangle="lower", mask_diagonal=True, title="Metric correlations", label="Pearson r")
```

## Multi-turn visual memory (`fm.Session`) & briefings (`fm.brief`)

```python
session = fm.Session(style="paper", state_path=".figmint_session.json")
f1 = session.explain("Alpha-3 leads baseline by 9.3 points", fm.compare({"Alpha-3": 86.4, "Baseline": 77.1}, highlight="Alpha-3", baseline="Baseline", unit="%"))
# Prefix matching: "Alpha-3 (int4)" automatically inherits "Alpha-3"'s hue on turn 2!
f2 = session.explain("Quantized Alpha-3 stays within 1.1 points at half the latency", fm.compare({"Alpha-3 (int4)": 85.3, "Baseline": 77.1}, highlight="Alpha-3 (int4)", baseline="Baseline", unit="%"))

# Compose into a single zero-CDN HTML report or PR-ready Markdown + PNGs
report = session.brief(
    "Release candidate evaluation",
    subtitle="Synthetic benchmark suite",
    summary=["Alpha-3 leads by 9.3 points", "int4 quantization retains 99% of accuracy"],
)
report.save("eval_brief.html")
report.save("eval_brief.md")   # writes eval_brief.md + eval_brief_figures/fig_01.png ...
```
