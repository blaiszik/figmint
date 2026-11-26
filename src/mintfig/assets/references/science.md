# mintfig: scientific data, sizing and colour

Read this file when the data has replicates or intervals, spans decades, carries units, has small n or missing values, when a multi-panel figure risks running too tall, or when colours have to hold across figures.

## Uncertainty: show it and name it

| You have | Use |
| :--- | :--- |
| Raw replicates per condition (seeds, wells, samples) | `mint.distribution`: every observation is drawn (`stat="mean"` if the claim is about means). For a countable frequency dotplot use `mode="quantile", quantiles=20` (5% per dot). |
| Raw replicates along x (dose, time, step) | `mint.trend(x, points={name: [[reps], ...]})`, or tidy `mint.trend("x", "group", y="val", data=rows)`, where repeated `(x, group)` rows become `points=` |
| Only an estimate and its interval | `mint.compare(error=..., inner_error=..., error_label="50% / 95% CI")` or `mint.trend(band=..., band_label="± 1 s.d.")` |

An unlabelled interval raises the `interval_unlabelled` warning. The facts report whether intervals overlap, the probability of exceeding `reference=`, and on `distribution` the empirical `P(group > baseline)`. Do not write "significant" unless you ran the test, and name the test in `note=`. The advisories `claim_overstates_uncertainty` and `claim_number_mismatch` flag clear mismatches between the takeaway and the facts.

## Axes, units and numbers

- **Values spanning decades:** use `log=True` for y (`compare`, `trend`, `distribution`) and `log_x=True` for x (`trend`, `relate`). Bars are never drawn on a log axis; they switch to dots.
- **Lower is better** (loss, error, IC50): `sort="asc"` puts the best item on top. In tables, use `sort="cost", bold_best="min"`.
- **Ratios against a reference:** `mint.compare(ratio, log=True, zero=False, reference=(1, "no change"), unit="×")`.
- **Units:** `unit=` is a short symbol (`ms`, `%`, `mg/L`, `×`), and words go in `label=`. Write Unicode directly (`µm`, `cm⁻³`, `°C`, `Å`, `χ²`), because `$...$` triggers `latex_markup`. Write fractional exponents as `"d⁻½"` or `"1/√d"`, never `"d⁻¹ᐟ²"`.
- **x unit:** on a numeric `trend` or `relate`, a one-word `(...)` or `[...]` at the end of `x_label` ("Time (h)") becomes the x unit in the facts ("4 h"). Override it with `x_unit="steps"`, or turn it off with `x_unit=""`.
- **Number format:** values get about 3 significant figures, `×10ⁿ` for extreme magnitudes, and are never rounded to zero. Override with `fmt=".2f"` or `fmt="{:.1f} ms"`.
- **Missing values:** pass `None` or `NaN`. They draw as gaps (`—` in `matrix` and `table`), are counted in the facts, and should be mentioned in `note=`.
- **Small n (< 5):** `distribution` draws the points and a centre mark only. State `n` in the title or `note=`.
- **More than 4 ordered levels** (doses, temperatures): `highlight=` the 1–3 that the claim is about (the rest become labelled grey context), or use `facet=True`.
- **Log-axis slopes:** with `trend(log=True)` and a numeric x, the facts report the log₁₀(y) slope per x unit with R², split around interior peaks and troughs. With `log_x=True` as well, they report power-law exponents with a 95% CI. `fit=True` draws the fit.

## Height and layout budgets

`too_tall` warns above 135 mm, which is one screen (at the 700 px chat width, 1 mm ≈ 5 px, so 675 px). A one-line takeaway plus one full-width panel is about:

| Panel | Figure height |
| :--- | :--- |
| `compare` or `share`, N bars | 23 + 5.3·N mm (5 → 50, 10 → 76, 20 → 129) |
| `distribution`, G groups | 33 + 8.5·G mm (4 → 67, 8 → 101) |
| `matrix`, R rows | 28 + 6.3·R mm (6 → 66, 10 → 90, 16 → 128) |
| `table`, R rows | 30 + 5.4·R mm (5 → 57, 10 → 84, 15 → 111) |
| `change`, N items | 60 mm at 4, 71 at 8, 99 at 14 |
| `trend` / `relate` | 79 / 84 mm full width, 66 at half width |

Each extra full-width row adds its own height minus about 15 mm. Side-by-side panels take the height of the tallest. `subtitle=` adds 4 mm, `source=` 6 mm, `note=` 4 mm, and a second takeaway line 5 mm. Give `matrix`, `table` and long-label panels a full row with `layout=[["a"], ["b", "c"]]`. `density="compact"` tightens rows.

## Colour

A name keeps one colour across every panel of a figure, so `"no retrieval"` stays red in a dot plot, a curve and a `mint.table` highlight. `highlight=` assigns red, blue, green and amber in that order unless a colour is pinned. Everything else turns grey, and `baseline=` is drawn in ink. To keep colours across figures in one conversation, pass `colors=summary["colors"]` (or `colors={"no retrieval": "red"}`) to the next `mint.explain`, or use `mint.Session`, which also matches name variants by prefix (see `recipes.md`).

- **Styles** (`style=`): `mintfig`, `bold`, `editorial`, `paper`, `dark`, `mono`, and `sketch`. `sketch` is for illustrations only and warns unless `source=` or `note=` says the data is illustrative.
- **Palettes** (`palette=`): `default`, `okabe_ito`, `tol`, `earth`, `ocean`, `berry`. Each is checked for colour-vision deficiency, independently of `style=`.

## Narrative levels

`summary["narrative"]` holds `L1` (what is drawn), `L2` (statistical facts), `L3` (perceptual patterns), `L4` (the domain takeaway), and a reader-first `summary` string. Use it for alt text or a spoken summary.
