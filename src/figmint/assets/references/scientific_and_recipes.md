# figmint Chat Figures: Scientific Details, Sizing & Recipes

Read this reference when building complex multi-panel scientific figures, sizing tight layouts, pinning entity colours across figures, or editing an existing figure spec.

## Scientific data guidance

- **Show uncertainty and name it:**
  | You have | Use |
  | :--- | :--- |
  | Raw replicates per condition (seeds, wells, samples) | `fm.distribution` — every observation drawn (`stat="mean"` if claim is about means) |
  | Raw replicates or units along x (dose, time, step) | `fm.trend(x, points={name: [[reps], ...]})` or tidy `fm.trend("x", "group", y="val", data=rows)` (repeated `(x, group)` rows auto-become `points=`) |
  | Only an estimate and its interval | `fm.compare(error=..., error_label="95% CI")` or `fm.trend(band=..., band_label="± 1 s.d.")` |

  An unlabelled interval triggers `interval_unlabelled`. `facts` state whether intervals overlap; do not write "significant" unless you ran the test, and name it in `note=`.
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
```

## Editing a returned figure (`fm.load`)

```python
spec = fm.load("ablation.png").to_spec()   # or read the .json written by write_spec=True
spec["takeaway"] = "Removing fine-tuning costs 13 points of accuracy, retrieval 8"
spec["panels"][0]["highlight"] = ["no fine-tuning"]
del spec["panels"][1]; spec.pop("layout", None)
print(fm.explain_from_spec(spec).save("ablation_v2.png", write_spec=True))
```
