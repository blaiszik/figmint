---
name: figmint
description: Explain data to a user with a message-first chat figure or table (one takeaway sentence plus evidence panels), or generate publication-ready Nature, Science, Cell, PNAS, NeurIPS, and screen-review scientific figures with exact millimeter geometry, preflight QA, clarity checks, and reproducible bundles.
---

# figmint — Figures That Say One Thing

> **Install:** `pip install git+https://github.com/blaiszik/figmint` (or `uv pip install ...`).

**Chat figures: read down to "Publication Figures" and stop.** Deep recipes & sizing: `references/scientific_and_recipes.md`; manuscripts: `references/publication.md`.

## Explain in a Conversation (`fm.explain`)

Use a chart for ≥5 numbers or a trend/spread/relationship; `fm.table` for exact lookups/scorecards; prose for 1–3 numbers.

**1. Write the takeaway first.** One sentence with its number ("Removing retrieval costs 8 points of accuracy", not "Ablation results"). One takeaway per figure.

**2. Pick each panel by the question it answers.** Every form accepts dicts/arrays/Series **and** tidy rows (`list[dict]` / DataFrame).

| Question | Form | Wide or tidy input |
| :--- | :--- | :--- |
| Compare sizes | `fm.compare(values)` | `{name: num}`, `{cat: {s: num}}`, or rows (`name=`, `value=`, `group=`) |
| Change over order/time | `fm.trend(x, series)` | `(x, {s: [nums]})` or `("x", "s", y="y", data=rows)` |
| Two states (before→after) | `fm.change(before, after)` | two `{name: num}` or `("c1", "c2", data=rows, name="item")` |
| Spread of raw values | `fm.distribution(groups)` | `{g: [obs]}` or rows (`group=`, `value=`; `bins=` / `fm.histogram`) |
| Two continuous measures | `fm.relate(x, y, x_label=, y_label=)` | two lists or `("x", "y", data=rows, names=, groups=)` |
| Part of whole | `fm.share(parts)` | `{name: num}` or rows (`name=`, `value=`) |
| Two categorical axes | `fm.matrix(values, rows=, cols=)` | 2-D array / wide DF, or rows (`rows=`, `cols=`, `value=`) |
| Exact lookup / scorecard | `fm.table(rows)` | `list[dict]`, DataFrame, `{col: [...]}`, or 2-D + `columns=` |
| Delta bridge start→total | `fm.waterfall(steps)` | `{step: delta}` or rows (`name=`, `value=`, optional `start=`) |
| Execution/phase spans | `fm.timeline(spans)` | `{stage: (start, end)}` or rows (`name=`, `start=`, `end=`, `group=`) |
| Cohort/pipeline attrition | `fm.flow(stages)` | `{stage: n}`, `[(stage, n, reason)]`, or rows (`name=`, `value=`, `reason=`) |

**3. Name what is measured and what matters:** `title=`, `label=`, `unit=`, `highlight=` (≤3; rest grey), `source=`.

```python
import figmint as fm

fig = fm.explain(
    "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
    fm.compare({"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
               error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77),
                      "no fine-tuning": (0.66, 0.72)},
               error_label="95% CI, 5 seeds",
               title="Both losses are outside seed noise", label="Test accuracy",
               highlight=["no retrieval", "no fine-tuning"]),
    fm.trend([0, 500, 1000, 1500, 2000],
             {"full model": [0.02, 0.61, 0.76, 0.80, 0.82],
              "no retrieval": [0.02, 0.52, 0.67, 0.72, 0.74],
              "no fine-tuning": [0.01, 0.44, 0.60, 0.66, 0.69]},
             title="The gap opens in the first 500 steps", label="Validation accuracy",
             x_label="Training step"),
    source="runs/ablation_2026-11 (5 seeds per variant)",
)
summary = fig.save("ablation.png")          # dict (print() renders JSON)
print(summary)
```

**Zero-script CLI:** `figmint inspect data.csv` profiles & recommends forms; `figmint plot data.csv --kind auto --takeaway "..." --out fig.png` (or explicit `--kind`, `--show`, `.html`) plots directly; `figmint edit fig.png --style dark --out v2.png` refines saved figures; `figmint brief f1.png f2.png --title "..." --out report.html` bundles multi-figure reports; `figmint explain` / `figmint show` handle JSON specs and terminal views.

**4. Check `facts` and `ship`, then deliver.**
- `summary` returns `panels[i]["facts"]`, `narrative` (L1–L4), `issues`, `ok`, and `ship`.
- **Read `facts` instead of recomputing:** forms compute rankings, baseline/reference gaps, interval overlaps, exceedance/`P(A > B)`, event medians, log slopes/power-law CIs, correlations, bottlenecks, and winners. Takeaway must agree with `facts` (`claim_overstates_uncertainty` / `claim_number_mismatch` warn advisories only).
- **`summary["ship"]` gates shipping:** `true` = zero errors and zero layout/text defects (overlaps, struck text, malformed `%`/minus/`nan`, missing glyphs, `$...$`, <11 px text). When `ship` is `true` and facts agree, **send immediately** — ignore advisory polish warnings.
- **Harness & output modes:** `width="chat"` (700 px), `width="narrow"` (450 px sidebar, auto-stacks), `width="slide"` (1280 px). `fig.save("out.html")` writes zero-CDN interactive HTML (`_repr_html_()` in Jupyter); `fig.to_terminal()` / `figmint show` renders in terminals.
- **Lenient mode:** `with fm.lenient():` / `strict=False` / `--lenient` auto-adjusts soft limits (logged in `adjustments`). Visual check if tight; cap fixes at ≤2 rounds.

### Every argument (unknown arguments raise `ExplainError` naming valid ones)

```python
fm.explain(takeaway, *panels,
    subtitle=None, source=None, note=None,  # scope and figure footer
    layout=None,            # e.g. [["a"], ["b", "c"]]; repeat key to widen
    colors=None,            # pin across figures: {"no retrieval": "red"} (blue/red/green/amber)
    style="figmint",        # "figmint" | "bold" | "editorial" | "paper" | "dark" | "mono" | "sketch"
    palette=None,           # "default" | "okabe_ito" | "tol" | "earth" | "ocean" | "berry"
    accent=None,            # custom primary highlight hex, e.g. "#D97757"
    strict=True,            # False / `with fm.lenient():`: auto-adjust soft limits
    width="chat")           # "narrow" (450 px), "chat" (700 px), "slide" (1280 px)

# Shared by every form: title=, label=, unit=, highlight= (1–3 names), fmt=
# compare, trend, distribution, table also take baseline= (control/"before", drawn in ink)

fm.compare(values,          # {name: num}, {cat: {s: num}}, Series, or rows
    name=None, group=None, value=None, sort=True, zero=True, log=False,
    error=None, inner_error=None, error_label=None,  # inner_error= inner CI inside error=
    boost=None, boost_label=None, show_delta=False,  # show_delta= inline (+delta) vs baseline=
    n=None, reference=None)

fm.trend(x, series=None,    # wide (x, {s: [nums]}) or tidy ("x", "s", y="y", data=rows)
    y=None, data=None, x_label=None, x_unit=None, log=False, log_x=False, zero=False,
    fit=False,              # True | "linear" | "log" | "power" overlays dashed regression fit
    band=None, band_label=None, points=None, points_label=None,
    events=None, regions=None, callouts=None,  # regions=[(x0, x1, txt)], callouts=[(x, y, txt)]
    reference=None, end_values=True, facet=False)

fm.change(before, after, data=None, name=None, labels=("Before", "After"))

fm.distribution(groups,     # {g: [obs]}, wide DF, or rows (group=/value=)
    group=None, value=None, stat="median",
    mode="dots", quantiles=20,  # mode="quantile" countable quantile dotplot (5–50 dots)
    bins=None, log=False, reference=None)

fm.histogram(values, group=None, value=None, bins="auto", stat="median", log=False, reference=None)

fm.relate(x, y, x_label=, y_label=, data=None, x_unit=None, names=None, groups=None,
    fit=False, frontier=False, label_all=False, connect_groups=False,
    regions=None, callouts=None, log_x=False, log_y=False, reference=None)

fm.share(parts, name=None, value=None, top=7)

fm.matrix(values, rows=None, cols=None, value=None, diverging=False, center=0.0,
    triangle=None, mask_diagonal=False, highlight=None)  # triangle="lower"|"upper" for symmetric matrices

fm.table(rows, columns=None, units=None, highlight=None, baseline=None,
    bold_best=False, sort=None, align=None, fmt=None)  # panel.to_markdown() exports MD

fm.waterfall(steps, name=None, value=None, start=None, total_label="Total", show_total=True, reference=None)

fm.timeline(spans, name=None, start=None, end=None, group=None, x_label=None, sort=True, reference=None)

fm.flow(stages, name=None, value=None, reason=None, show_pct=True)

fm.custom(draw_fn, height_mm=48.0, describe="...")  # escape hatch: draw_fn(ax)
```

### Limits, edits & multi-turn workflows (`references/scientific_and_recipes.md`)

- **Hard limits (strict):** `compare`/`timeline`/`table` ≤20, `change`/`waterfall` ≤14, `flow` ≤12, `distribution` ≤8 groups (≥3 obs), `matrix` ≤16×12, `table` ≤8 cols, `relate(groups=)` ≤4, `trend` ≤4 coloured series (else `highlight=`/`facet=True`, ≤12), `highlight=` ≤3, 4 shared colours, ≤6 panels, `too_tall` >135 mm.
- **Rules:** zero-baseline bars (`zero=False`/`error=`/`log=True` → dots); no pies, dual axes, legends, or rotated text; name every interval (`error_label=`/`band_label=`); direct Unicode (`µm`, `cm⁻³`, `°C` — never `$...$`).
- **Auto, edits & memory:** `fm.auto_panel("data.csv")` picks form/columns; `fm.edit("fig.png", highlight=..., drop=..., style=..., out="v2.png")`; `s = fm.Session(style=..., state_path=...)` keeps colours across turns (prefix-matching variants); `s.brief("Title").save("report.html"|"report.md")` bundles reports.

## Publication Figures

For manuscripts (`nature`, `science`, `science_advances`, `cell`, `pnas`, `neurips`, `screen`), read **`references/publication.md`** for exact journal specs, script contract, and Tufte primitives. Quick workflow:

1. Write `plot.py` exposing `def build(journal="nature") -> fm.Plate` (or top-level `plate`/`fig`) using `fm.Plate` or `fm.figure`.
2. Run preflight + bundle export:
   ```bash
   figmint run plot.py --journal nature --bundle out/ --json
   ```
3. Exit `0` (`ok: true`) → show `out/preview.png` (and `out/proof.png`); exit `1` → fix `severity == "error"` via `fix_hint` (**max 2 repair loops**); exit `2` → fix script contract/exception.
4. Apply Tufte discipline (`fm.ghost_context`, `fm.slopegraph`, `fm.range_frame`, `fm.direct_labels`); never use rainbow/jet colormaps or `bbox_inches="tight"`.
