---
name: figmint
description: Explain data to a user with a message-first chat figure (one takeaway sentence plus evidence panels), or generate publication-ready Nature, Science, Cell, PNAS, NeurIPS, and screen-review scientific figures with exact millimeter geometry, preflight QA, clarity checks, and reproducible bundles.
---

# figmint — Figures That Say One Thing

Two jobs, two paths:

- **Explaining a result to a person in a conversation** → `fm.explain` (next section). Use this by default.
- **A manuscript or report figure** (`nature`, `science`, `science_advances`, `cell`, `pnas`, `neurips`, `screen`) → the script contract and `figmint run`, further down.

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
- `facts` are computed from the data (highest and lowest, ratios, differences from the highlighted item, whether intervals overlap, first-to-last change, medians, r, missing values). **Your takeaway must agree with them**; if it does not, fix the sentence, not the chart.
- A trend's `a → b from x0 to x1` fact is the two endpoint values: for noisy daily data it misleads. Check claims against the event, baseline and median facts instead.
- `issues` lists warnings with a `fix_hint` each. `ok: false` means an error-level issue; the PNG is still written so you can see it.
- **Open the PNG.** The checks do not catch every collision or awkward label; your eyes are the last check. Fix what the issues and your look turn up, in at most two rounds of re-rendering (a call rejected with an error before anything is drawn does not count), then show it with any remaining caveat stated.

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
    reference=None)         # (value, "label") line

fm.trend(x, series,         # x: numbers, dates/ISO strings, or ordered labels; series: {name: [numbers]}, None for gaps
                            # (omit series when points= supplies the data: fm.trend(x, points={...}))
    x_label=None,           # end it with the x unit in brackets, "Time after dose (h)": facts then say "19 h", not "19"
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
    names=None,             # one name per point; highlight= then labels those points
    groups=None,            # one group label per point (at most 4) -> coloured, directly labelled;
                            # facts give the pooled r and each group's r;
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

`fig.save("x.png", write_spec=True)` also writes `x.json`. Inputs may be dicts, lists, numpy arrays, pandas Series or DataFrames: `trend(df.index, df)` takes a wide frame (index = x, one column per series; `df.pivot(index="date", columns="region", values="p99")`); `compare`, `change` and `share` take a Series (index = names); `distribution` takes a dict of lists or a wide frame (one column per group, NaN dropped), not a long frame; `matrix` takes a frame (index = rows, columns = cols).

**Before/after an event:** `fm.trend(x, series, events={"2026-10-15": "config change"}, highlight=["us-west"])` — facts give each coloured series' median before the event and from it on, with the change. For the day-to-day spread, add `fm.distribution({"before": [...], "after": [...]}, baseline="before")`.

### Scientific data

- **Show the uncertainty, and say what it is.**

  | You have | Use |
  | :--- | :--- |
  | Raw replicates per condition (seeds, wells, samples) | `fm.distribution` — every observation is drawn; `stat="mean"` if your claim is about means |
  | Raw replicates along x (dose, time, step) | `fm.trend(x, points={name: [[reps], ...]})` — mean line with every replicate as a dot |
  | Only an estimate and its interval | `fm.compare(error=..., error_label="95% CI")` or `fm.trend(band=..., band_label="± 1 s.d.")` |

  An interval without `error_label=`/`band_label=` raises a warning: a whisker nobody can interpret is worse than none. `facts` say in plain words whether two intervals overlap; do not write "significant" unless you ran the test, and then name it in `note=`.
- **Values spanning decades:** `log=True` puts the measured value on a log axis in `compare`, `trend` and `distribution` (conductivity, counts, an Arrhenius plot against 1000/T). `log_x=True` on `trend` and `relate` is for an x that spans decades (dose, frequency). Bars are never drawn on a log axis.
- **Lower is better** (loss, error, IC50): `sort="asc"` puts the best item on top.
- **Units and symbols:** write Unicode directly — `unit="µm"`, `"cm⁻³"`, `"°C"`, `"Å"`, `label="χ²"`. `$...$` is not math here. A character the font cannot draw is reported as `glyph_missing`.
- **Numbers** are shown to about three significant figures, with `×10ⁿ` for very large or small values, and are never rounded to zero. Override with `fmt=".2f"` or `fmt="{:.1f} ms"`. The unit is printed once, on the first value.
- **Missing values:** pass `None` or NaN. Gaps are drawn as gaps, counted in `facts`, and belong in `note=`.
- **Small n:** groups with fewer than five observations show the points and a centre mark only; say n in the title or note.
- **More than four ordered levels** (five doping levels, six doses): colour the one to three the claim is about with `highlight=` and let the rest be labelled grey context, or use `facet=True`. There is no colour ramp for lines.
- **Derived numbers** (fits, IC50, activation energies) are yours to compute; say how in `source=` or `note=`, and check them against `facts` where a fact covers them (crossings of a `reference=` value, fold changes, slopes on log axes).
- **Log-axis slopes:** with `trend(log=True)` and numeric x, `facts` give the least-squares slope of log₁₀(y) per x unit with R². A series that rises then falls (absorption then elimination, a doping optimum) is fitted separately up to and from its peak, never across it; quote the side your claim is about.

### Colour

A name keeps one colour in every panel of a figure, so "no retrieval" is the same red in the dot plot and in the curve beside it. `highlight=` decides who is emphasised: colours go red, blue, green, amber in highlight order unless pinned, and a lone unhighlighted series is blue. A `baseline=` (control, "before") is drawn in ink, so it never takes the red. To keep a name's colour the same across several figures in one conversation, pass `colors={"no retrieval": "red", "full model": "blue"}` to each `fm.explain` call; the summary's `colors` key reports what the last figure used, ready to pass on.

### Rules the forms enforce (do not work around them)

- One takeaway per figure; one claim per panel. Up to four panels is comfortable, six is the limit. Use several only when the argument has steps (what, since when, why). A `too_tall` warning (taller than one screen, roughly two rows of charts) means split it into two figures.
- Bars start at zero and are sorted. When zero is meaningless pass `zero=False` for a dot plot. Intervals are drawn as dots with whiskers, never inside bars.
- At most four series get a colour. With more, `highlight=` the ones that matter or `facet=True` for small multiples on a shared scale.
- No pies, no dual axes, no legends (labels sit on the data), no rotated text.
- The chat column is about 700 px wide: keep `width="chat"`. A wider canvas is scaled down and its text shrinks.
- Layout defaults: two panels side by side, three as one wide row over two, four as 2×2. Matrices and long names need width: give them a full row with `layout=`.
- Styles (`style=`, JSON `"style"`, CLI `--style`) change the surface only, never the rules: `figmint` (default, white ground), `bold` (heavy lines on matte gray, for one strong comparison), `editorial` (serif headline, dotted gridlines, for multi-panel arguments), `sketch` (hand-drawn, for conceptual or illustrative points only; it warns unless `source=`/`note=` says the data is illustrative).

### When a figure comes back

Every PNG carries its own spec. If the person returns a figure (or another agent hands you one) and asks for a change, rebuild it instead of redrawing from memory:

```python
fig = fm.load("ablation.png")        # or a .json spec
spec = fig.to_spec()                 # the takeaway, panels and data as plain JSON: edit and pass to fm.explain_from_spec(spec)
```

`figmint explain --show-spec ablation.png` prints the same spec. Chat apps that re-encode images drop it, so keep the `.json` (`write_spec=True`) when the figure matters.

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
