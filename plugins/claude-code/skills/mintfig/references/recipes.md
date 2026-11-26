# mintfig: recipes

Worked code to copy from. `rows` is a `list[dict]` or a DataFrame; each section stands alone, so jump to the one you need.

- [Tidy rows and tables](#tidy-rows-and-tables)
- [Model-release charts](#model-release-charts)
- [Intervals, deltas, regions and fits](#intervals-deltas-regions-and-fits)
- [Waterfall, timeline and flow](#waterfall-timeline-and-flow)
- [Editing a saved figure](#editing-a-saved-figure)
- [Several figures: sessions and briefs](#several-figures-sessions-and-briefs)
- [HTML and terminal output](#html-and-terminal-output)

## Tidy rows and tables

```python
mint.compare(rows, name="model", value="score", error=("ci_lo", "ci_hi"), error_label="95% CI", n="n")
mint.trend("step", "variant", y="val_acc", data=rows, x_label="Training step", label="Accuracy")
mint.distribution(rows, group="condition", value="ic50", log=True, label="IC50", unit="µM")
mint.matrix(rows, rows="model", cols="benchmark", value="score", label="Pass rate", unit="%")
mint.relate("cost", "score", data=rows, names="model", groups="family", log_x=True,
          x_label="Cost ($/M tokens)", y_label="Score (%)")

# A scorecard with mixed units and the best value per column in bold
mint.table(
    rows,
    columns=["Model", "GPQA", "SWE-bench", "Cost"],
    units={"GPQA": "%", "SWE-bench": "%", "Cost": "$/M"},
    bold_best={"GPQA": "max", "SWE-bench": "max", "Cost": "min"},
    highlight="New Model",
    baseline="Prev Gen",
    sort="-GPQA",
    title="New Model leads reasoning and coding at half the cost",
)

# Each unit as % of its own median before an event, against an untreated control
wide = df.pivot(index="time", columns="unit_id", values="value")
rel = wide / df[df.time < t_event].groupby("unit_id").value.median() * 100
mint.trend(rel.index, rel, baseline="untreated", events={t_event: "event"},
         label="Value vs own median before", unit="%")
```

## Model-release charts

Pair these with `width="slide"`, `style="paper"` or `"dark"`, and `accent="#D97757"` for wide hero graphics.

```python
# Grouped benchmarks
mint.compare(
    {"GPQA": {"New": 86.4, "Prev": 77.1, "Peer": 83.2}, "SWE": {"New": 74.2, "Prev": 58.6, "Peer": 71.0}},
    highlight="New", baseline="Prev", label="Accuracy", unit="%", title="Head-to-head benchmarks",
)
# Extended-thinking boost stacked on the base score
mint.compare(
    {"New": 76.0, "Prev": 64.0, "Peer": 74.0},
    boost={"New": 10.4, "Prev": 6.2, "Peer": 8.0}, boost_label="Extended thinking",
    highlight="New", baseline="Prev", label="AIME accuracy", unit="%",
)
# Cost-performance Pareto frontier
mint.relate(
    "cost", "score", data=rows, names="model", groups="family", highlight="NewFamily",
    frontier=True, label_all=True, connect_groups=True, log_x=True,
    x_label="Cost ($/M tokens)", y_label="Score (%)", unit="%",
)
```

## Intervals, deltas, regions and fits

```python
# Countable quantile dotplot against a control and a target
mint.distribution(
    {"treated": treated_samples, "control": control_samples},
    mode="quantile", quantiles=20, baseline="control", reference=(50, "target"),
    highlight="treated", label="Response", unit="%", title="90% of treated runs clear target",
)
# Nested 50% / 95% intervals with deltas against the control
mint.compare(
    {"variant A": 84.2, "variant B": 79.1, "control": 74.9},
    error={"variant A": 3.4, "variant B": 3.1, "control": 2.9},
    inner_error={"variant A": 1.6, "variant B": 1.5, "control": 1.4},
    error_label="50% / 95% CI", baseline="control", show_delta=True,
    highlight="variant A", label="Accuracy", unit="%",
)
# A shaded window and a callout on a time series
mint.trend(
    days, {"service": latency}, x_label="Day", label="p99 latency", unit="ms",
    regions=[(10, 14, "migration window")],
    callouts=[(12, 420, "cache cold-start spike")],
)
# Fitted scaling curves, and a lower-triangle correlation matrix
mint.trend(compute, {"Dense": loss_d, "MoE": loss_m}, log=True, log_x=True, fit=True,
         x_label="Compute (FLOPs)", label="Validation loss")
mint.matrix(corr, rows=metrics, cols=metrics, diverging=True, center=0.0,
          triangle="lower", mask_diagonal=True, title="Metric correlations", label="Pearson r")
```

## Waterfall, timeline and flow

```python
# Delta bridge (ablation gains, cost or latency budgets)
mint.waterfall(
    {"+RAG": 8.0, "+Reranker": 3.4, "+CoT": 2.1, "Quantization": -1.5},
    start=("Base model", 69.0), total_label="Shipped", highlight="+RAG",
    reference=(80.0, "Release target"),
    title="RAG drives 67% of the net gain", label="Benchmark accuracy", unit="%",
)
# Phase spans (CI traces, agent runs, protocols): (name, start, end, group)
mint.timeline(
    [("fetch", 0, 8, "setup"), ("compile", 8, 54, "build"), ("unit tests", 54, 92, "verify"),
     ("integration", 54, 148, "verify"), ("deploy", 148, 160, "release")],
    highlight="integration", reference=(120, "CI SLA"),
    title="Integration tests exceed the 120 s budget", x_label="Elapsed (s)", unit="s",
)
# Attrition with exclusion reasons: (stage, n, reason)
mint.flow(
    [("Screened", 1240), ("Eligible", 912, "missing baseline"),
     ("Enrolled", 780, "declined consent"), ("Completed", 714, "lost to follow-up")],
    highlight="Eligible", title="58% of screened patients complete follow-up",
    label="Cohort size", unit="patients",
)
```

## Editing a saved figure

`mint.edit` takes a saved PNG (the spec is embedded), a JSON spec or an `Explanation`, and changes only what you name. `mint.load(path)` returns the figure itself.

```python
mint.edit(
    "ablation.png",
    takeaway="Removing fine-tuning costs 13 points of accuracy, retrieval 8",
    highlight="no fine-tuning",
    drop_panel="b",               # or drop= / keep= item names
    style="dark",
    out="ablation_v2.png",
    write_spec=True,
)
# mintfig edit ablation.png --highlight "no fine-tuning" --drop-panel b --style dark --out ablation_v2.png
```

`mint.auto_panel("data.csv")` picks a form and columns for a file. `mintfig inspect` and `mintfig plot --kind auto` do the same from the shell.

## Several figures: sessions and briefs

```python
session = mint.Session(style="paper", state_path=".mintfig_session.json")
f1 = session.explain("Alpha-3 leads baseline by 9.3 points",
    mint.compare({"Alpha-3": 86.4, "Baseline": 77.1}, highlight="Alpha-3", baseline="Baseline", unit="%"))
# "Alpha-3 (int4)" inherits Alpha-3's colour by prefix match
f2 = session.explain("Quantized Alpha-3 stays within 1.1 points at half the latency",
    mint.compare({"Alpha-3 (int4)": 85.3, "Baseline": 77.1}, highlight="Alpha-3 (int4)", baseline="Baseline", unit="%"))

report = session.brief(
    "Release candidate evaluation",
    subtitle="Synthetic benchmark suite",
    summary=["Alpha-3 leads by 9.3 points", "int4 quantization retains 99% of accuracy"],
)
report.save("eval_brief.html")   # one self-contained page
report.save("eval_brief.md")     # eval_brief.md + eval_brief_figures/fig_01.png ...
```

Outside a session, `mint.brief("Title", "prose", fig1, "## Section", fig2, ...)` mixes prose, headings and figures (or saved PNGs and specs) in order. The CLI equivalent is `mintfig brief f1.png f2.png --title "..." --out report.html`.

## HTML and terminal output

- **HTML:** `fig.save("review.html")` (or `mintfig explain spec.json --out review.html`) writes one self-contained file with no CDN. It switches layouts at 360 px, 450 px and full width, follows the reader's light or dark setting, shows each mark's value, interval and n on hover, and has a `data · svg · spec` line under the figure. Notebooks render it through `_repr_html_()`. For a page holding several figures, use `fig.to_html()` fragments or `mint.brief`.
- **Terminal:** `fig.to_text()` is the plain surface that `deliver["text"]` holds. `fig.to_terminal()` adds colour, and `mintfig show fig.png` (also a spec or `-`, with `--mode auto|kitty|iterm2|unicode|ascii`) draws inline images in Kitty, Ghostty, iTerm2 or WezTerm and falls back to Unicode bars, tables and sparklines.
