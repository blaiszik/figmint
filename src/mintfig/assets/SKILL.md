---
name: mintfig
description: Use when showing a person five or more numbers (benchmarks, ablations, comparisons, trends, distributions, CSV/experiment outcomes, profiles, logs) so they get a message-first figure or table via mint.explain, mint.table, or `mintfig plot data.csv` with computed facts and a ship gate; before sharing any plain Matplotlib figure, script, or notebook (`mint.check`, `mintfig check plot.py`, `analysis.ipynb`); or for journal/manuscript plates (Nature, Science, Cell, PNAS, NeurIPS) needing exact mm geometry and preflight QA. Do NOT use for routine code edits, bug fixes, refactoring, unit tests, git operations, stack traces, architecture explanations, config/Docker changes, or replies with 1–3 scalar numbers (answer those in prose).
---

# mintfig: figures that say one thing

Install: `pip install mintfig`, `mintfig skill --install --global`, and optionally `mintfig hook --install` for automatic Matplotlib checks. Read only what the task needs:

| Task | Read |
| :--- | :--- |
| A figure or table for a person (most tasks) | This file, down to "Publication Figures", then stop |
| Intervals, replicates, log axes, units, small n, height budgets, colours across figures, styles | `references/science.md` |
| Worked code: tidy rows, scorecards, model-release charts, waterfall/timeline/flow, `mint.edit`, `mint.Session`, `mint.brief`, HTML/terminal | `references/recipes.md` |
| A manuscript or journal plate | `references/publication.md` |

## Explain in a Conversation (`mint.explain`)

Draw a chart for five or more numbers or any comparison, trend, spread, or relationship. Use `mint.table` for exact lookups. Do NOT plot for 1–3 scalar numbers or routine coding tasks (bug fixes, refactors, tests, git, stack traces, config) — reply in prose.

**1. Write the takeaway first.** One sentence with its number ("Removing retrieval costs 8 points of accuracy", not "Ablation results") becomes the title. Each figure gets one takeaway.

**2. Pick each panel by the question it answers.** Every form accepts dicts, arrays, Series, or tidy rows (`list[dict]` or a DataFrame).

| Question | Form | Wide or tidy input |
| :--- | :--- | :--- |
| Compare sizes | `mint.compare(values)` | `{name: num}`, `{cat: {s: num}}`, or rows (`name=`, `value=`, `group=`) |
| Change over order/time | `mint.trend(x, series)` | `(x, {s: [nums]})` or `("x", "s", y="y", data=rows)` |
| Two states (before→after) | `mint.change(before, after)` | two `{name: num}` or `("c1", "c2", data=rows, name="item")` |
| Spread of raw values | `mint.distribution(groups)` | `{g: [obs]}` or rows (`group=`, `value=`); `mint.histogram` for bins |
| Two continuous measures | `mint.relate(x, y, x_label=, y_label=)` | two lists or `("x", "y", data=rows, names=, groups=)` |
| Part of whole | `mint.share(parts)` | `{name: num}` or rows |
| Two categorical axes | `mint.matrix(values, rows=, cols=)` | 2-D array, wide DF, or rows (`rows=`, `cols=`, `value=`) |
| Exact lookup / scorecard | `mint.table(rows)` | `list[dict]`, DataFrame, `{col: [...]}`, or 2-D + `columns=` |
| Bridge from start to total | `mint.waterfall(steps)` | `{step: delta}` or rows |
| Phase or execution spans | `mint.timeline(spans)` | `{stage: (start, end)}` or rows |
| Cohort or pipeline attrition | `mint.flow(stages)` | `{stage: n}` or `[(stage, n, reason)]` |

**3. Name what is measured and what matters:** `label=`, `unit=`, `highlight=` (at most 3; the rest turn grey), `baseline=` (control, drawn in ink; facts compare against it), `source=`. Name every interval (`error_label=`, `band_label=`). Write units in Unicode (`µm`, `cm⁻³`, `°C`), never `$...$`.

```python
import mintfig as mint

fig = mint.explain(
    "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
    mint.compare({"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
               error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77),
                      "no fine-tuning": (0.66, 0.72)},
               error_label="95% CI, 5 seeds",
               title="Both losses are outside seed noise", label="Test accuracy",
               highlight=["no retrieval", "no fine-tuning"]),
    mint.trend([0, 500, 1000, 1500, 2000],
             {"full model": [0.02, 0.61, 0.76, 0.80, 0.82],
              "no retrieval": [0.02, 0.52, 0.67, 0.72, 0.74],
              "no fine-tuning": [0.01, 0.44, 0.60, 0.66, 0.69]},
             title="The gap opens in the first 500 steps", label="Validation accuracy",
             x_label="Training step"),
    source="runs/ablation_2026-11 (5 seeds per variant)",
)
summary = fig.save("ablation.png")          # dict; print() shows a compact JSON view
print(summary)
```

Without Python: `mintfig inspect data.csv` recommends forms, and `mintfig plot data.csv --kind auto --takeaway "..." --out fig.png` draws one.

**4. Check the summary, then ship.**
- Read `summary["panels"][i]["facts"]` instead of recomputing (rankings, baseline gaps, interval overlap, `P(A > B)`, slopes, crossings). The takeaway must agree with them.
- If `summary["ship"]` is `true` (no errors, overlaps, struck/malformed text, or text < 11 px), send it now and ignore advisory warnings. Otherwise apply each `fix_hint` (at most 2 rounds). `summary["advisories"]` (`low_density`) are suggestions, not blockers.
- An `ExplainError` names its rule and fix. For quick charts, `strict=False` or `with mint.lenient():` auto-adjusts soft limits and lists changes in `summary["adjustments"]`.
- `print(summary)` is compact; `json.dumps(summary)` holds every key (`narrative`, `alt_text`, `colors`, `display`).

**5. Put it in front of the reader.** `summary["deliver"]` holds `markdown` (relative image line), `caption` (fact behind the takeaway), `text` (plain, ≤ 72 cols), and `html` (once saved as `.html`).

| Where the reply lands | Render with | Send |
| :--- | :--- | :--- |
| Chat that renders images | default `width="chat"` (700 px) | `deliver["markdown"]` |
| Phone or IDE sidebar (~450 px) | `width="narrow"` (panels stack) | `deliver["markdown"]` |
| Artifact host or review page | `fig.save("fig.html")` | file at `deliver["html"]` |
| Plain terminal or unknown | (any) | `deliver["text"]` in a code fence |
| Notebook | (any) | return `fig` |
| Slide or PR | `width="slide"` (1280 px) for slides | PNG (by repo path in a PR) |

Reply with the sentence, the figure, and the caption — nothing more:

```markdown
Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13.

![Removing retrieval costs 8 points of accuracy; …](ablation.png)

*No retrieval −0.08 vs full model (0.82); no fine-tuning −0.13 vs full model (0.82).*
```

If unsure which surface you're on, `fig.show()` picks one and `mintfig doctor` reports what works here.

### Already drawn with Matplotlib (`mint.check`)

Before sharing any plain Matplotlib figure, script, or notebook, check it: `report = mint.check(fig, "claim sentence", dpi=<dpi>)`, `mintfig check plot.py --python .venv/bin/python`, or `mintfig check analysis.ipynb` (exit `0` ship, `1` fix, `2` error; `--python` auto-detects project `.venv`). It reads plotted values back from bars, lines, heatmaps, histograms, bands, and boxplots, checks claim numbers against them, and measures text at `width=` (`"chat"` 700 px, `"narrow"`, `"slide"`). Apply each `fix_hint` until `report["ship"]` is `true`. Use `mintfig hook --install` to run this automatically after agent plot writes.

### Every argument (unknown arguments raise `ExplainError` naming valid ones)

```python
mint.explain(takeaway, *panels,
    subtitle=None, source=None, note=None,  # scope and figure footer
    layout=None,            # e.g. [["a"], ["b", "c"]]; repeat a key to widen
    colors=None,            # pin across figures: {"no retrieval": "red"} (blue/red/green/amber)
    color_names=True, density="regular",  # names coloured in titles; "compact": tighter rows
    style="mintfig",        # "mintfig" | "bold" | "editorial" | "paper" | "dark" | "mono" | "sketch"
    palette=None,           # "default" | "okabe_ito" | "tol" | "earth" | "ocean" | "berry"
    accent=None,            # custom primary highlight hex, e.g. "#D97757"
    strict=True,            # False / `with mint.lenient():`: auto-adjust soft limits
    width="chat")           # "narrow" (450 px), "chat" (700 px), "slide" (1280 px)

# Shared by every form: title=, label=, unit=, highlight= (1–3 names), fmt=
# compare, trend, distribution, table also take baseline= (control/"before", drawn in ink)

mint.compare(values,          # {name: num}, {cat: {s: num}}, Series, or rows
    name=None, group=None, value=None, sort=True, zero=True, log=False,
    error=None, inner_error=None, error_label=None,  # inner_error= inner CI inside error=
    boost=None, boost_label=None, show_delta="auto",  # auto: bracket a gap the takeaway states
    n=None, reference=None, facet=False, legend=False)

mint.trend(x, series=None,    # wide (x, {s: [nums]}) or tidy ("x", "s", y="y", data=rows)
    y=None, data=None, x_label=None, x_unit=None, log=False, log_x=False, zero=False,
    fit=False,              # True | "linear" | "log" | "power": dashed regression fit
    band=None, band_label=None,  # band={s: (lo, hi)}, each a list along x
    points=None, points_label=None,  # raw replicates: points={s: [[reps at x0], [reps at x1], ...]}
    events=None, regions=None, callouts=None,  # regions=[(x0, x1, txt)], callouts=[(x, y, txt)]
    reference=None, end_values=True, facet=False, legend=False)

mint.change(before, after, data=None, name=None, labels=("Before", "After"))

mint.distribution(groups,     # {g: [obs]}, wide DF, or rows (group=/value=)
    group=None, value=None, stat="median",
    mode="dots", quantiles=20,  # mode="quantile": countable quantile dotplot (5–50 dots)
    bins=None, log=False, reference=None, facet=False)

mint.histogram(values, group=None, value=None, bins="auto", stat="median", log=False, reference=None, facet=False)

mint.relate(x, y, x_label=, y_label=, data=None, x_unit=None, names=None, groups=None,
    fit=False, frontier=False, label_all=False, connect_groups=False,
    regions=None, callouts=None, log_x=False, log_y=False, reference=None, facet=False,
    legend=False)

mint.share(parts, name=None, value=None, top=7, kind="bars")  # "bars" | "pie" | "donut" (<=5)

mint.matrix(values, rows=None, cols=None, value=None, diverging=False, center=0.0,
    triangle=None, mask_diagonal=False, highlight=None)  # triangle="lower"|"upper" for symmetric

mint.table(rows, columns=None, units=None, highlight=None, baseline=None,
    bold_best=False, sort=None, align=None, fmt=None, bars=None, interval=None,
    interval_label=None, spark=None)  # panel.to_markdown() exports Markdown

mint.waterfall(steps, name=None, value=None, start=None, total_label="Total", show_total=True, reference=None)

mint.timeline(spans, name=None, start=None, end=None, group=None, x_label=None, sort=True, reference=None)

mint.flow(stages, name=None, value=None, reason=None, show_pct=True)

mint.custom(draw_fn, height_mm=48.0, describe="...")  # escape hatch: draw_fn(ax)
```

### Limits

- **Strict limits** (`ExplainError` in strict mode): `compare`/`timeline`/`table` ≤ 20 items, `change`/`waterfall` ≤ 14, `flow` ≤ 12, `distribution` ≤ 8 groups (≥ 3 obs each), `matrix` ≤ 16×12, `table` ≤ 8 columns, `relate(groups=)` ≤ 4 (12 with `facet=True`), `trend` ≤ 4 coloured series (use `highlight=` or `facet=True`, up to 12). Max 3 highlights, 4 shared colours, 6 panels; `too_tall` warns > 135 mm.
- `scales_differ` means two panels share a measure on different ranges — merge into one `facet=` panel.
- Revise with `mint.edit("fig.png", highlight=..., drop=..., out="v2.png")`, keep colours across turns with `mint.Session`, and combine into reports with `mint.brief(...)` (`references/recipes.md`).

## Publication Figures

For manuscripts (`nature`, `science`, `science_advances`, `cell`, `pnas`, `neurips`, `screen`), read `references/publication.md` for journal specs, the script contract and Tufte primitives. In short:

1. Write `plot.py` exposing `def build(journal="nature") -> mint.Plate` (or a top-level `plate`/`fig`).
2. Run `mintfig run plot.py --journal nature --bundle out/ --json`.
3. Exit `0` means show `out/preview.png`. Exit `1` means fix each `severity == "error"` issue with its `fix_hint`, for at most 2 rounds. Exit `2` means fix the script contract or the exception.
4. Use the Tufte helpers `mint.pub.ghost_context`, `mint.pub.slopegraph`, `mint.pub.range_frame` and `mint.pub.direct_labels`. Never use rainbow/jet colormaps or `bbox_inches="tight"`.
