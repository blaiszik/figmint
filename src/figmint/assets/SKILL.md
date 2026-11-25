---
name: figmint
description: Explain data to a user with a message-first chat figure or table (one takeaway sentence plus evidence panels), or generate publication-ready Nature, Science, Cell, PNAS, NeurIPS, and screen-review scientific figures with exact millimeter geometry, preflight QA, clarity checks, and reproducible bundles.
---

# figmint — Figures That Say One Thing

> **Not installed yet?** `pip install git+https://github.com/blaiszik/figmint` (or `uv pip install git+https://github.com/blaiszik/figmint`).

**Chat figures: read down to "Publication Figures" and stop.** For deep scientific recipes, height budgets, and colour/spec editing details, read `references/scientific_and_recipes.md`; for full manuscript rules, read `references/publication.md`.

## Explain in a Conversation (`fm.explain`)

Use a chart when the reader must compare ≥5 numbers or see a trend, spread, or relationship; use `fm.table` for exact lookups or multi-metric scorecards; use a sentence for 1–3 numbers.

**1. Write the takeaway first.** One sentence with its number ("Removing retrieval costs 8 points of accuracy", not "Ablation results"). One takeaway per figure.

**2. Pick each panel by the question it answers.** Every form accepts dicts/arrays/Series **and** row-shaped data (`list[dict]` from `csv.DictReader`/`json.loads`, or tidy `pandas.DataFrame`).

| Question | Form | Wide or tidy input |
| :--- | :--- | :--- |
| How do items differ in size? | `fm.compare(values)` | `{name: num}` or `rows, name="col", value="col"` |
| How does it change over time/order? | `fm.trend(x, series)` | `(x, {name: [nums]})` or `("x_col", "series_col", y="y_col", data=rows)` |
| What moved between two states? | `fm.change(before, after)` | two `{name: num}` or `("col1", "col2", data=rows, name="item")` |
| How are raw values spread? | `fm.distribution(groups)` | `{name: [obs]}` or `rows, group="col", value="col"` (add `bins="auto"` or use `fm.histogram`) |
| Do two measures move together? | `fm.relate(x, y, x_label=, y_label=)` | two lists or `("x_col", "y_col", data=rows, names="...", groups="...")` |
| What makes up the total? | `fm.share(parts)` | `{name: num}` or `rows, name="col", value="col"` |
| How do two categories interact? | `fm.matrix(values, rows=, cols=)` | 2-D values / wide DataFrame, or `rows, rows="r", cols="c", value="v"` |
| Exact lookup or mixed-unit scorecard? | `fm.table(rows)` | `list[dict]`, DataFrame, `{col: [...]}`, or 2-D list + `columns=` |

**3. Say what is measured and what matters.** Pass `title=`, `label=`, `unit=`, `highlight=` (up to 3; rest turn grey), and `source=`.

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
summary = fig.save("ablation.png")          # already-parsed dict; print() renders JSON
print(summary)
```

No Python handy? Render JSON directly: `figmint explain spec.json --out fig.png` (or `--out fig.html` for interactive HTML; `--example` prints a starter spec; `-` reads stdin; `--lenient` auto-adjusts soft limits). Display directly in a terminal with `figmint show fig.png` (or `spec.json` / `-`; auto-detects Kitty/iTerm2 graphics or falls back to Unicode/ASCII).

**4. Check `facts` and `ship`, then deliver.**
- `summary` is a dict (`summary["panels"][i]["facts"]`, `summary["narrative"]` L1–L4, `summary["issues"]`, `summary["ok"]`, `summary["ship"]`).
- **Read `facts` before computing anything in Python/scipy:** forms compute rankings, gaps vs `baseline=`/`reference=`, interval overlaps, exceedance/`P(A > B)` superiority, before/after event medians, log-axis slopes/power-law exponents with 95% CI, group correlations, and table leaders. **Your takeaway must agree with `facts`** (advisory checks `claim_overstates_uncertainty` and `claim_number_mismatch` warn on clear mismatches without blocking `ship`).
- **`summary["ship"]` gates shipping:** `true` means zero errors and zero drawn-layout or text defects (including drawn-text overlaps, lines crossing text, malformed `%`/minus/`nan`, missing glyphs, LaTeX `$...$`, and sub-11 px chat text). When `summary["ship"]` is `true` and the takeaway agrees with `facts`, **send the figure right away** — do not re-render for advisory polish warnings (`many_items`, `too_tall`, `unit_is_long`).
- **Match the user's harness:** `width="chat"` (700 px default), `width="narrow"` (450 px IDE sidebars — auto-stacks multi-panel vertically), `width="slide"` (1280 px hero/slides). Save interactive HTML via `fig.save("out.html")` (embedded SVG + Facts drawer + Critique/Ask-Agent snippet; Jupyter displays via `_repr_html_()`), or render terminal views with `fig.to_terminal()` / `figmint show`.
- **Fast lenient mode:** wrap ad-hoc charts in `with fm.lenient():` (or `strict=False` / `--lenient`) to auto-facet >4 trend series, trim oversized lists, auto-stack cramped/wide panels, and move advisory warnings to `summary["advisories"]` (changes logged in `summary["adjustments"]`).
- **Visual check & cap:** open the PNG when layout is tight; fix issues in at most 2 re-render rounds, then show the image plus 1–2 sentences adding cause, caveat, or next step.

### Every argument (unknown arguments raise `ExplainError` naming valid ones)

```python
fm.explain(takeaway, *panels,
    subtitle=None, source=None, note=None,  # scope and figure-level footer
    layout=None,            # e.g. [["a"], ["b", "c"]]; repeat key to widen: [["a", "a", "b"]]
    colors=None,            # pin across figures: {"no retrieval": "red"} (blue, red, green, amber)
    style="figmint",        # "figmint" | "bold" | "editorial" | "paper" | "dark" | "mono" | "sketch"
    palette=None,           # "default" | "okabe_ito" | "tol" | "earth" | "ocean" | "berry"
    accent=None,            # custom primary highlight hex color, e.g. "#D97757"
    strict=True,            # False / `with fm.lenient():`: auto-adjust soft limits
    width="chat")           # "narrow" (450 px sidebar, auto-stacks), "chat" (700 px), "slide" (1280 px)

# Shared by every form: title=, label=, unit=, highlight= (1–3 names), fmt=
# compare, trend, distribution, table also take baseline= (control/"before", drawn in ink)

fm.compare(values,          # {name: num}, {cat: {series: num}} (grouped), Series, or rows
    name=None, group=None, value=None, sort=True, zero=True, log=False,
    error=None, inner_error=None, error_label=None,  # inner_error= thicker inner CI inside error=
    boost=None, boost_label=None, show_delta=False,  # show_delta= inline (+delta) vs baseline=
    n=None, reference=None)  # error=/inner_error=/boost=/n= also accept column name(s)

fm.trend(x, series=None,    # wide (x, {name: [nums]} / DataFrame) or tidy ("x_col", "s_col", y="y_col", data=rows)
    y=None, data=None, x_label=None, x_unit=None, log=False, log_x=False, zero=False,
    band=None, band_label=None, points=None, points_label=None,
    events=None, regions=None, callouts=None,  # regions=[(x0, x1, txt)], callouts=[(x, y, txt)] (<=4)
    reference=None, end_values=True, facet=False)

fm.change(before, after,    # two {name: num} or ("col1", "col2", data=rows, name="item")
    data=None, name=None, labels=("Before", "After"))

fm.distribution(groups,     # {name: [obs]}, wide DataFrame, or rows with group=/value=
    group=None, value=None, stat="median",
    mode="dots", quantiles=20,  # mode="quantile" draws stacked countable quantile dotplot (5–50 dots)
    bins=None, log=False, reference=None)

fm.histogram(values,        # alias for distribution(..., bins=bins); single list, <=4 groups, or rows
    group=None, value=None, bins="auto", stat="median", log=False, reference=None)

fm.relate(x, y, x_label=, y_label=,   # two lists, or column names with data=rows
    data=None, x_unit=None, names=None, groups=None, fit=False,
    frontier=False,         # True/"upper-left" | "upper-right" | "lower-left" | "lower-right" Pareto envelope
    label_all=False,        # label every point (requires names=, <=24 points) with collision avoidance
    connect_groups=False,   # connect points within each group in x order (e.g. model generation trajectories)
    regions=None, callouts=None,  # shaded x spans [(x0, x1, txt)] & direct leader notes [(x, y, txt)]
    log_x=False, log_y=False, reference=None)

fm.share(parts,             # {name: >=0 num}, Series, or rows with name=/value=
    name=None, value=None, top=7)

fm.matrix(values,           # 2-D array / wide DataFrame, or tidy rows with rows="r", cols="c", value="v"
    rows=None, cols=None, value=None, diverging=False, center=0.0, highlight=None)

fm.table(rows,              # list[dict], DataFrame, {col: [...]}, or 2-D list + columns=
    columns=None, units=None, highlight=None, baseline=None,
    bold_best=False,        # True/"max" | "min" | {col: "max"|"min"} bolds numeric column winners
    sort=None, align=None, fmt=None)  # sort="col" (asc) / "-col" (desc); panel.to_markdown() exports MD

fm.custom(draw_fn, height_mm=48.0, describe="...")  # last resort: draw_fn(ax)
```

### Core rules & limits (details & recipes in `references/scientific_and_recipes.md`)

- **Hard limits (strict mode):** `compare` ≤20, `change` ≤14, `distribution` ≤8 groups (≥3 obs each), `matrix` ≤16×12, `table` ≤20×8, `relate(groups=)` ≤4, `trend` ≤4 coloured series (else `highlight=` or `facet=True`, ≤12), `highlight=` ≤3 per panel, 4 shared entity colours per figure, ≤6 panels (warns >4), height warns `too_tall` >135 mm.
- **Perceptual rules:** bars start at zero (`zero=False` or `error=`/`log=True` → dots); no pies, dual axes, legends, or rotated text; always name intervals (`error_label=`/`band_label=`); write Unicode directly (`µm`, `cm⁻³`, `°C`, `χ²` — never `$...$`).
- **Round-trip edits:** every PNG embeds its spec (`spec = fm.load("fig.png").to_spec()`, edit, then `fm.explain_from_spec(spec)`). Use `write_spec=True` to also save `.json`.

## Publication Figures

For manuscripts (`nature`, `science`, `science_advances`, `cell`, `pnas`, `neurips`, `screen`), read **`references/publication.md`** for exact journal specs, script contract, and Tufte primitives. Quick workflow:

1. Write `plot.py` exposing `def build(journal="nature") -> fm.Plate` (or top-level `plate`/`fig`) using `fm.Plate` or `fm.figure`.
2. Run preflight + bundle export:
   ```bash
   figmint run plot.py --journal nature --bundle out/ --json
   ```
3. Exit `0` (`ok: true`) → show `out/preview.png` (and `out/proof.png`); exit `1` → fix `severity == "error"` via `fix_hint` (**max 2 repair loops**); exit `2` → fix script contract/exception.
4. Apply Tufte discipline (`fm.ghost_context`, `fm.slopegraph`, `fm.range_frame`, `fm.direct_labels`); never use rainbow/jet colormaps or `bbox_inches="tight"`.
