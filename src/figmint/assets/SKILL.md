---
name: figmint
description: Explain data to a user with a message-first chat figure (one takeaway sentence plus evidence panels), or generate publication-ready Nature, Science, Cell, PNAS, NeurIPS, and screen-review scientific figures with exact millimeter geometry, preflight QA, clarity checks, and reproducible bundles.
---

# figmint — Figures That Say One Thing

**Chat figures: read down to the "Publication Figures" heading and stop.** Everything after it is for manuscripts.

- **Explaining a result to a person in a conversation** (the default) → `fm.explain`, next section.
- **A manuscript or report figure** (`nature`, `science`, `science_advances`, `cell`, `pnas`, `neurips`, `screen`) → the script contract and `figmint run`, from the "Publication Figures" heading on.

## Explain in a Conversation (`fm.explain`)

Use a figure when the reader must compare five or more numbers, or see a trend, a spread or a relationship. One to three numbers belong in a sentence; exact lookups belong in a table.

**1. Write the takeaway first.** One sentence, with its number, stating what the reader should conclude ("Removing retrieval costs 8 points of accuracy", not "Ablation results"). If you cannot write it, you do not have a figure yet. One takeaway per figure: a question with three answers gets three small figures, each with its own sentence, not one figure with a three-clause title.

**2. Pick each panel by the question it answers.** The form applies the encoding rules for you.

| Question the panel answers | Form | You pass |
| :--- | :--- | :--- |
| How do items differ in size? | `fm.compare(values)` | `{name: number}` |
| How does it change over time, dose, step or order? | `fm.trend(x, series)` | x values, `{name: [numbers]}` |
| What moved between two states? | `fm.change(before, after)` | two `{name: number}` |
| How are raw values spread within groups? | `fm.distribution(groups)` | `{name: [observations]}` |
| Do two measures move together? | `fm.relate(x, y, x_label=, y_label=)` | two lists |
| What makes up the total? | `fm.share(parts)` | `{name: number}` |
| How do two categorical dimensions interact? | `fm.matrix(values, rows=, cols=)` | 2-D values |

**3. Say what is measured and what matters.** Every form takes `title=` (the panel's own claim), `label=` and `unit=` (what is measured), and `highlight=` (the one to three names the takeaway is about; everything else turns grey).

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
    source="runs/ablation_2026-11 (5 seeds per variant)",   # say if synthetic or estimated
)
summary = fig.save("ablation.png")          # a dict (summary["facts"] etc.); print() shows it as JSON
print(summary)
```

No Python handy? The same figure as JSON: `figmint explain spec.json --out fig.png` (`figmint explain --example` prints a spec to start from; `-` reads stdin). Exit code `2` means the spec broke a rule and nothing was drawn: apply `fix_hint`.

**4. Check the summary, then look at the image.**

- `summary` is a plain dict, already parsed (do not `json.loads` it): `summary["panels"][i]["facts"]`, `summary["issues"]`, `summary["ok"]`.
- `facts` are computed from the data; read them before computing anything. `compare`: highest, lowest, their ratio or range; each highlighted item's rank and gap to the `reference=`, `baseline=` or next item (signed values: its place above or below zero, and the others' range); with `error=`, which intervals overlap it, or each interval against the reference; `n=` counts. `trend`: each series' first → last and peak, spikes against its median, gaps and crossings between coloured series, crossings of a `reference=`, medians before and from each event, gaps to a baseline, one line on the grey series; `log=True` adds slopes of log₁₀(y) with R², and with `log_x=True` power-law exponents with 95% CI. `distribution`: centre, spread, range and n per group, far values, each highlighted group's gap to and separation from the others (or the baseline). `relate`: r and n per group, then pooled; `fit=True` adds each slope with 95% CI. `change`: the largest change, how many rose and fell, the rest's range. `share`: total, largest, top 3, each highlighted part (and their sum). `matrix`: extremes, highest and lowest row and column means, an outlier cell. Do not import scipy or refit what a fact states; compute only what no fact covers. **Your takeaway must agree with them**; if it does not, fix the sentence, not the chart. A trend's `a → b from x0 to x1` fact is just the two endpoints, misleading for noisy daily data: check claims against the event, baseline and median facts.
- `issues` lists warnings with a `fix_hint` each. `ok: false` means an error-level issue; the PNG is still written so you can see it.
- **Open the PNG**: your eyes are the last check for collisions and awkward labels. Fix what the issues and your look turn up in at most two rounds of re-rendering (a call rejected before drawing does not count), then show it with any remaining caveat stated.

**5. Hand it over.** Show the image, then one or two sentences that add what the figure cannot (cause, caveat, next step). Do not re-describe the chart. Use `alt_text` when the channel needs a text equivalent.

### Every argument (anything else is rejected with a hint naming the right one)

```python
fm.explain(takeaway, *panels,
    subtitle=None,          # scope: what, where, when
    source=None, note=None, # footer: where the numbers came from; caveats (figure level, not per panel)
    layout=None,            # e.g. [["a"], ["b", "c"]]; repeat a key to widen: [["a", "a", "b"]]
    colors=None,            # pin a name to a colour across figures: {"no retrieval": "red"} (blue, red, green, amber)
    style="figmint",        # "figmint" | "bold" | "editorial" | "sketch"
    width="chat")           # keep "chat" in a conversation

# Shared by every form: title=, label=, unit=, highlight= (a name or a list of up to 3), fmt=
# compare, trend, distribution also take baseline= (a control or "before"): drawn in ink, not
#   highlighted; facts then state every highlighted (or every other) item against it

fm.compare(values,          # {name: number}
    sort=True,              # True/"desc" largest first | "asc" smallest first (lower is better) | False keep order
    zero=True,              # False -> dot plot when zero is meaningless
    log=False,              # True -> dots on a log axis, for values spanning decades
    error=None,             # {name: (low, high)} absolute bounds, or {name: half_width}, or one number for all
    error_label=None,       # what the interval is: "95% CI", "± 1 s.d., n = 5"  (always give it with error=)
    n=None,                 # {name: count} -> "n=84" under each name and in the facts; keep names plain
    reference=None)         # (value, "label") line

fm.trend(x, series,         # x: numbers, dates/ISO strings, or ordered labels; series: {name: [numbers]}, None for gaps
                            # (omit series when points= supplies the data: fm.trend(x, points={...}))
    x_label=None,           # end it with the x unit in brackets, "Time after dose (h)": facts then say "19 h", not "19"
    x_unit=None,            # the x unit when x_label's bracket is not one ("Step (batch 2)"): x_unit="steps"; "" for none
    log=False, log_x=False, # log value (y) axis / log x axis; an Arrhenius plot is log=True against 1000/T
    zero=False,             # True forces the y axis to include zero
    band=None,              # {name: (low_list, high_list)} or {name: half_width}; band_label= says what it is
    band_label=None,
    points=None,            # raw replicates {name: [[reps at x0], [reps at x1], ...]} -> arithmetic-mean line + dots
    events=None,            # {x_value: "short label"} vertical markers; any x on a numeric axis, not only data points
    reference=None,         # (value, "label") horizontal line
    end_values=True,        # False keeps the name at the line end but drops the last value
    facet=False)            # True -> small multiples on one shared scale (for more than 4 series)

fm.change(before, after,    # two {name: number} with the same names
    labels=("Before", "After"))

fm.distribution(groups,     # {name: [raw observations]}, at least 3 per group; groups keep the order given
    stat="median",          # "median" (median and middle half) | "mean" (mean and ± 1 s.d.)
    log=False, reference=None)

fm.relate(x, y, x_label=, y_label=,   # both required; y_label is the panel's measure line
    x_unit=None,            # as on trend; unit= (shared) is the y unit, used in the slope facts
    names=None,             # one name per point; highlight= then labels those points
    groups=None,            # one group label per point (at most 4) -> coloured, directly labelled;
                            # facts give each group's r (with fit=, its slope and 95% CI), then the pooled r;
                            # highlight= may name a group (the others turn grey but stay labelled)
    fit=False,              # least-squares line (per group if groups=), r and n reported
    log_x=False, log_y=False,
    reference=None)         # (value, "label") horizontal line

fm.share(parts,             # {name: non-negative number}
    top=7)                  # smaller parts fold into "Other"

fm.matrix(values, rows=[...], cols=[...],   # 2-D list/array (or a DataFrame: rows/cols come from it)
    diverging=False, center=0.0,           # True for signed data such as correlations or differences
    highlight=None)         # ("row", "col"), a list of such pairs, or a row/column name

fm.custom(draw_fn, height_mm=48.0, describe="...")   # draw_fn(ax): last resort when no form fits
```

`fig.save("x.png", write_spec=True)` also writes `x.json`. Inputs may be dicts, lists, numpy arrays, pandas Series or DataFrames: `trend(df.index, df)` takes a wide frame (index = x, one column per series; `df.pivot(index="date", columns="region", values="p99")`); `compare`, `change` and `share` take a Series (index = names); `distribution` takes a dict of lists or a wide frame (one column per group, NaN dropped), not a long frame; `matrix` takes a frame (index = rows, columns = cols). `events=` keys use the x's own type: a number on a numeric x, an ISO string (`"2026-03-01"`) or date on a date x, the label text on a labelled x.

### Limits and sizes (plan the layout before rendering)

Past a hard limit the call is rejected before anything is drawn, with a `fix_hint`:

- **Forms:** `compare` 20 items (warns above 12), `change` 14 items, `distribution` 8 groups of at least 3 values, `matrix` 16 rows × 12 cols, `relate(groups=)` 4 groups. `trend`: more than 4 series need `highlight=` (1 to 3) or `facet=True` (at most 12 series; a `baseline=` is not counted). `share` keeps the `top=7` largest (all of them if only one more is left) and folds the rest into "Other (n)", which `highlight=` cannot name.
- **Figure:** `highlight=` takes 3 names per panel (`matrix`: 3 cells, rows or columns in all). 4 colours per figure, shared by all panels: every highlighted name, coloured trend series and `relate` group takes one, and a fifth reuses one (`colour_reused_across_panels` warning); `colors=` pins at most 4. 6 panels (warns above 4). The takeaway wraps to at most 3 lines (aim for about 100 characters).
- **Room:** labels that leave too little room for the data (`panel_too_small`, `matrix_cells_too_small`) are rejected too: give the panel a full row with `layout=`, or shorten names.

**Height.** `too_tall` warns above 135 mm, one screen (the `screen` spec's `max_height_mm`; at the 700 px chat width 1 mm ≈ 5 px, so 675 px). A one-line takeaway plus one full-width panel is about:

| Panel | Figure height |
| :--- | :--- |
| `compare` or `share`, N bars | 23 + 5.3·N mm (5 → 50, 10 → 76, 20 → 129) |
| `distribution`, G groups | 33 + 8.5·G mm (4 → 67, 8 → 101) |
| `matrix`, R rows | 28 + 6.3·R mm (6 → 66, 10 → 90, 16 → 128) |
| `change`, N items | 60 mm at 4, 71 at 8, 99 at 14 |
| `trend` / `relate` | 79 / 84 mm full width, 66 at half width |

Each further full-width row adds its own height less about 15 mm; panels side by side are as tall as the tallest; `subtitle=` adds 4 mm, `source=` 6, `note=` 4, a second takeaway line 5. So above or below a full-width trend fit at most a 9-item compare, a 4-group distribution or a 6-row matrix; a 2×2 of trends and 5-item compares is about 110 mm. A 20-item compare or an 8-group distribution needs its own figure or a place beside, not above, the other panel.

### Scientific data

- **Show the uncertainty, and say what it is.**

  | You have | Use |
  | :--- | :--- |
  | Raw replicates per condition (seeds, wells, samples) | `fm.distribution` — every observation is drawn; `stat="mean"` if your claim is about means |
  | Raw replicates or units along x (dose, time, step) | `fm.trend(x, points={name: [[reps], ...]})` — the way to show every replicate or unit: mean line plus each as a dot |
  | Only an estimate and its interval | `fm.compare(error=..., error_label="95% CI")` or `fm.trend(band=..., band_label="± 1 s.d.")` |

  An interval without `error_label=`/`band_label=` raises a warning: a whisker nobody can interpret is worse than none. `facts` say in plain words whether two intervals overlap; do not write "significant" unless you ran the test, and then name it in `note=`.
- **Values spanning decades:** `log=True` for the measured value (`compare`, `trend`, `distribution`; conductivity, counts, an Arrhenius plot against 1000/T), `log_x=True` for an x that spans decades (`trend`, `relate`; dose, frequency). Bars are never drawn on a log axis.
- **Lower is better** (loss, error, IC50): `sort="asc"` puts the best item on top.
- **Units:** `unit=` is a short symbol (`ms`, `%`, `mg/L`, `×`); words go in `label=` (`label="Share of own baseline", unit="%"`). Write Unicode directly — `unit="µm"`, `"cm⁻³"`, `"°C"`, `"Å"`, `label="χ²"`. `$...$` is not math here. A character the font cannot draw is reported as `glyph_missing`: write a fractional exponent as `"d⁻½"` or `"1/√d"`, never `"d⁻¹ᐟ²"`.
- **x unit:** in `trend` (numeric x) and `relate`, a one-word `(...)` or `[...]` at the end of `x_label` is read as the x unit and printed after every x in `facts` ("Time (h)" gives "4 h"); a bracket with a space or a leading digit ("Step (batch 2)", "Load (2x)") is not. `x_unit="steps"` sets it, `x_unit=""` turns it off.
- **Numbers** are shown to about three significant figures, with `×10ⁿ` for very large or small values, and are never rounded to zero. Override with `fmt=".2f"` or `fmt="{:.1f} ms"`. The unit is printed once, on the first value.
- **Missing values:** pass `None` or NaN. Gaps are drawn as gaps, counted in `facts`, and belong in `note=`.
- **Small n:** groups with fewer than five observations show the points and a centre mark only; say n in the title or note.
- **More than four ordered levels** (five doping levels, six doses): `highlight=` the one to three the claim is about (the rest are labelled grey context) or `facet=True`. There is no colour ramp for lines.
- **Derived numbers** (fits, IC50, activation energies) are yours to compute; say how in `source=` or `note=`, and check them against `facts` where a fact covers them (crossings of a `reference=` value, fold changes, slopes on log axes).
- **Log-axis slopes:** with `trend(log=True)` and numeric x, `facts` give the least-squares slope of log₁₀(y) per x unit with R². A series that rises then falls (absorption then elimination, a doping optimum) is fitted separately up to and from its peak, never across it; quote the side your claim is about.

### Recipes

Patterns by data shape and question; rename to your data. `df` is long (columns `group`, `item`, `unit_id`, `time`, `x`, `value`); `wide = df.pivot(index="time", columns="unit_id", values="value")`.
```python
# A ratio per item, against a reference: dots on a log axis around 1; facts read as ratios
fm.compare(ratio, log=True, zero=False, reference=(1, "no change"), label="Ratio to reference", unit="×")
# Replicates along an ordered x (one row per measurement): mean line plus every replicate
xs = sorted(df.x.unique())
pts = {g: [s.loc[s.x == v, "value"].tolist() for v in xs] for g, s in df.groupby("group")}
fm.trend(xs, points=pts, label="Value", x_label="Setting (V)")
# Two groups, compare the tails: one row per percentile (beside fm.distribution(groups) for the spread)
pct = {g: {f"p{q}": float(np.percentile(v, q)) for q in (50, 90, 99)} for g, v in groups.items()}
fm.change(pct["A"], pct["B"], labels=("A", "B"), label="Value", unit="s")
# Several series, before/after an event: facts give each coloured series' median before and from it on
fm.trend(wide.index, wide, events={t_event: "event"}, highlight=["u3"], label="Value", unit="s")
fm.distribution({"before": [...], "after": [...]}, baseline="before", label="Value", unit="s")  # one series
# Before/after an event, with an untreated comparison: each unit as % of its own median before
rel = wide / df[df.time < t_event].groupby("unit_id").value.median() * 100
fm.trend(rel.index, rel, baseline="untreated", events={t_event: "event"}, label="Value vs own median before", unit="%")
# A value per item, many items in a few categories: raw ratios (not log₂) on a log axis; top item in the title
by = df.groupby("group").value.apply(list).to_dict()
top = df.loc[df.value.idxmax()]
fm.distribution(by, log=True, reference=(1, "no change"), label="Ratio to reference", unit="×",
                title=f"Highest: {top['item']} ({top.value:.2g}×)")
```

### Colour

A name keeps one colour in every panel of a figure, so "no retrieval" is the same red in the dot plot and in the curve beside it. `highlight=` decides who is emphasised: colours go red, blue, green, amber in highlight order unless pinned; everything else turns grey (in a `distribution`, the highlighted groups' dots take colours and the rest are grey; in a `trend(points=)`, the other series' replicate dots too: when every series' replicates matter, leave `highlight=` off so all of them, up to four, keep a colour), and a lone unhighlighted series is blue. A `baseline=` (control, "before") is drawn in ink, never in red. To keep colours across several figures in one conversation, pass `colors={"no retrieval": "red", "full model": "blue"}` to each `fm.explain` call; the summary's `colors` key reports what the last figure used, ready to pass on.

### Rules the forms enforce (do not work around them)

- One takeaway per figure; one claim per panel. Use several panels only when the argument has steps (what, since when, why). A `too_tall` warning means split it into two figures.
- Bars start at zero and are sorted; negative values in `compare` run left from zero (diverging bars), so pass signed differences as they are. When zero is meaningless pass `zero=False` for a dot plot. Intervals are drawn as dots with whiskers, never inside bars. A `reference=` outside the data extends the axis to include it.
- No pies, no dual axes, no legends (labels sit on the data), no rotated text.
- The chat column is about 700 px wide: keep `width="chat"`. A wider canvas is scaled down and its text shrinks.
- Layout defaults: two panels side by side, three as one wide row over two, four as 2×2. Matrices and long names need width: give them a full row with `layout=`.
- Styles (`style=`, JSON `"style"`, CLI `--style`) change the surface only, never the rules: `figmint` (default, white ground), `bold` (heavy lines on matte gray, for one strong comparison), `editorial` (serif headline, dotted gridlines, for multi-panel arguments), `sketch` (hand-drawn, for conceptual or illustrative points only; it warns unless `source=`/`note=` says the data is illustrative).

### When a figure comes back

Every PNG carries its own spec (`figmint explain --show-spec ablation.png` prints it; chat apps that re-encode images drop it, so keep the `.json` from `write_spec=True` when the figure matters). If the person returns a figure (or another agent hands you one) and asks for a change, edit the spec instead of redrawing from memory. An edit may change the top-level keys `takeaway`, `subtitle`, `note`, `source`, `layout`, `colors` and `style` (set a missing one to add it) and any form argument in `panels[i]`:

```python
spec = fm.load("ablation.png").to_spec()   # or a .json spec: {"takeaway", "layout", "panels": [{"kind", ...}], ...}
spec["takeaway"] = "Removing fine-tuning costs 13 points of accuracy, retrieval 8"
spec["panels"][0]["highlight"] = ["no fine-tuning"]   # panel keys are the form's own arguments
del spec["panels"][1]; spec.pop("layout")            # dropping a panel: drop the layout too
print(fm.explain_from_spec(spec).save("ablation_v2.png", write_spec=True))
```

## Publication Figures: Standard Agent Workflow

1. Write a self-contained Python plotting script (`plot.py`) following the **script contract** below.
2. Run preflight + export bundle in one command:
   ```bash
   figmint run plot.py --journal nature --bundle out/ --json
   ```
   (Supports `--journal nature|science|science_advances|cell|pnas|neurips|screen` and optional `--width`.)
3. Inspect the JSON output (`schema_version: "0.2"`):
   - Exit code `0` (`ok: true`): figure passes all deterministic journal rules. Review any clarity `warning` items (`color_separation`, `clarity_metadata`), then show `out/preview.png` (and `out/proof.png` for colorblind/print verification) to the user.
   - Exit code `1` (`stage: "preflight"`): read `issues` where `severity == "error"`, apply each item's `fix_hint` using `panel`, `panels`, `elements`, and `element_locations`, and re-run.
   - Exit code `2` (`stage: "contract"` or `"runtime"`): fix the script contract or Python exception using `error` and `fix_hint`, then re-run.
4. **2-Loop Repair Cap**: perform **at most 2 repair loops**. Never loop indefinitely. If an error remains after 2 passes, stop, report the remaining `issues` clearly, and show `out/preview.png` so the user can guide the layout trade-off.

## Script Contract

`figmint run` discovers your figure cleanly in this priority order:

1. A module-level `def build(...) -> fm.Plate | matplotlib.figure.Figure:` function (may optionally accept `journal` and/or `width` arguments).
2. A module-level `plate` (`figmint.Plate`) or `fig` (`matplotlib.figure.Figure`) variable.

Optional module-level metadata automatically flows into `figure.tex` and `figure.json`:
- `CAPTION: str` — manuscript figure caption (written to `figure.tex` and `figure.json`)
- `LABEL: str` — LaTeX `\label{...}` (default `"fig:fig1"`)
- `TAKEAWAY: str` — one-sentence human takeaway stored in `figure.json`
- `PANEL_NOTES: dict[str, str]` — one-line reading per panel stored in `figure.json`

Always use `fm.Plate` for multi-panel figures or `fm.figure` for single-panel figures:

```python
import numpy as np
import figmint as fm


def build(journal: str = "nature") -> fm.Plate:
    plate = fm.Plate(journal=journal, width="double", height_mm=105.0, layout=(1, 2))
    x = np.linspace(0, 10, 200)
    plate["a"].plot(x, np.exp(-x / 3.0), label="Control")
    plate["a"].plot(x, np.exp(-x / 6.0), label="Treated")
    plate["a"].set_xlabel("Time (h)")
    plate["a"].set_ylabel(r"Signal ($\mu\mathrm{M}$)")
    fm.direct_labels(plate["a"])

    rng = np.random.default_rng(0)
    plate["b"].scatter(rng.normal(size=200), rng.normal(size=200), s=8, alpha=0.7)
    plate["b"].set_xlabel("PC 1")
    plate["b"].set_ylabel("PC 2")

    plate.label_panels()
    return plate
```

## Journal Specs Quick Reference

| Journal | Width Presets (mm) | Max Height | Body / Tick / Panel | Panel Case |
| :--- | :--- | :---: | :---: | :---: |
| `nature` | `single`: 89, `mid`/`1.5col`: 120, `double`/`full`: 183 | 170 mm | 6.5 / 6.0 / 8.0 pt | `a, b, c` |
| `science` | `single`: 55, `double`/`2col`: 120, `full`/`3col`: 184 | 180 mm | 7.0 / 6.0 / 8.5 pt | `A, B, C` |
| `science_advances` | `single`: 84, `mid`: 120, `double`/`full`: 175 | 180 mm | 7.0 / 6.0 / 8.5 pt | `A, B, C` |
| `cell` | `single`: 85, `mid`/`1.5col`: 114, `double`/`full`: 174 | 200 mm | 7.0 / 6.0 / 8.5 pt | `A, B, C` |
| `pnas` | `single`: 87, `mid`/`1.5col`: 114, `double`/`full`: 178 | 200 mm | 7.0 / 6.5 / 9.0 pt | `A, B, C` |
| `neurips` | `half`/`single`: 67, `mid`: 111.8, `double`/`full`: 139.7 | 180 mm | 7.5 / 6.5 / 8.5 pt | `a, b, c` |
| `screen` | `chat`/`single`: 140, `wide`/`double`: 180, `slide`: 240 | 135 mm | 8.5 / 7.5 / 10.0 pt | `a, b, c` |

## Tufte & Editorial Visual Grammar

Optimize for **dense human comprehension**, not just journal compliance:

- **Small multiples over spaghetti (*"Compared to what?"*):** If a panel needs `> 4` curves, split into shared-axis small multiples and draw muted peer curves behind each panel with `fm.ghost_context(...)`.
- **High-density comparative forms:** Use `fm.slopegraph(...)` for paired before/after across 6–20 categories (not clustered bars), `fm.sparkline(...)` for compact multi-metric training telemetry, and `fm.tufte_boxplot(...)` for distributions (not opaque dynamite bars).
- **Maximize data-ink & trim spines:** Use `fm.range_frame(ax, rug=True)` so continuous spines span exact data `[min, max]`; never box legends (`frameon=False`); prefer `fm.direct_labels(ax)` (which trims the bottom spine back to the data) and in-place annotations (`n`, slopes, regime splits).
- **Micro/macro layering & restrained color:** Keep large background fills and CI ribbons pale (`alpha <= 0.14`); reserve saturated accent ink strictly for small high-signal focal elements; recede background curves with `fm.emphasize(ax, keep=...)`.
- **Graphical integrity (zero lie factor):** Start positive bar charts at zero; scale bubble markers by **area** (`s ∝ value`), never radius; always display uncertainty (`± SD` / `95% CI`) and sample size `n`.

## Publication Best Practices

- Never use rainbow/jet colormaps (`jet`, `rainbow`, `hsv`, `gist_rainbow`, `nipy_spectral`, `prism`, `flag`); use perceptual colormaps (`viridis`, `magma`, `cividis`, `inferno`, `figmint_navy`, `figmint_teal`, `figmint_div`).
- Never pass `bbox_inches="tight"` when saving — `figmint` locks exact millimeter MediaBox dimensions via `constrained_layout`.
- Variables in mathtext default to italic (`$T$`, `$P$`, `$\rho$`); wrap units in `\mathrm{...}` (e.g., `r"$\mathrm{\mu m}$"`).
- Bundle outputs in `out/`: `figure.pdf` (Type 42 editable vector), `figure.svg`, `preview.png`, `proof.png` (CVD + grayscale proof), `figure.tex`, `figure.json` (message-first sidecar), `reproduce.py`, and `report.json`.
