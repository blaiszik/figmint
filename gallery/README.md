# figmint Gallery

Visual examples of every primary function in `figmint`, rendered directly from the scripts in this folder (all datasets are synthetic).

- **Conversation figures (`fm.explain`)**: [Multi-panel `fm.explain`](#fmexplain--multi-panel-arguments) · [`fm.compare`](#fmcompare--size-and-intervals) · [`fm.trend`](#fmtrend--change-over-time-dose-or-scale) · [`fm.change`](#fmchange--paired-before-and-after) · [`fm.distribution`](#fmdistribution--raw-observations-and-spread) · [`fm.relate`](#fmrelate--two-continuous-measures) · [`fm.share`](#fmshare--part-of-a-whole) · [`fm.matrix`](#fmmatrix--two-categorical-dimensions) · [Visual styles (`style=`)](#visual-styles-style) · [Editing & CLI (`fm.load`)](#editing-returned-figures-and-cli)
- **Publication figures (`fm.figure`, `fm.Plate`, `figmint run`)**: [Before vs. After](#before-vs-after-default-matplotlib) · [Journal plates](#multi-panel-publication-plates)

---

## `fm.explain` — Multi-panel arguments

Combine two to four panels when an argument has steps (*what*, *since when*, *how spread*, *so what*). One entity name keeps one colour across every panel, and `fig.save()` returns computed `facts` for each panel to verify the takeaway.

### Two-panel scientific ablation (`fm.compare` + `fm.trend`)

![Ablation study with 95% CIs and training curves](output/explain_science/ablation.png)

*Source: [`explain_science_examples.py`](explain_science_examples.py)*

### Three-panel materials optimum (`fm.compare` log + `fm.trend` Arrhenius + `fm.compare`)

![Doping optimum across conductivity, Arrhenius curves, and activation energy](output/explain_science/doping_optimum.png)

*Source: [`explain_science_examples.py`](explain_science_examples.py)*

### Four-panel incident story (`fm.compare` + `fm.trend` + `fm.distribution` + `fm.share`)

![Four-panel latency regression story](output/explain/checkout_story.png)

*Source: [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `fm.compare` — Size and intervals

Sorted bars from zero by default; switches automatically to dots with whiskers when `error=`, `zero=False`, or `log=True` is passed. Use `baseline=` to draw a control in ink and state every highlighted item against it in `facts`, and `n=` to show sample sizes under each name.

### Signed effects with 95% CIs, `n=`, `baseline=`, and `reference=`

![Signed treatment effect compare plot with 95% CIs and n counts](output/explain_forms/compare_intervals.png)

```python
fm.explain(
    "High-dose therapy cuts HbA1c by 1.4 points, 1.6 points below placebo",
    fm.compare(
        {"High dose": -1.4, "Standard dose": -0.7, "Low dose": -0.3,
         "Diet only": -0.1, "Placebo": 0.2},
        error={"High dose": (-1.7, -1.1), "Standard dose": (-1.0, -0.4),
               "Low dose": (-0.6, 0.0), "Diet only": (-0.4, 0.2), "Placebo": (-0.1, 0.5)},
        error_label="95% CI",
        n={"High dose": 62, "Standard dose": 60, "Low dose": 58, "Diet only": 55, "Placebo": 61},
        reference=(0, "no change"), baseline="Placebo", highlight="High dose",
        sort="asc", label="Change in HbA1c at 24 weeks", unit="%", fmt="+.1f",
        title="Both active doses stay well below zero",
    ),
    source="synthetic example data",
)
```

*Source: [`explain_form_gallery.py`](explain_form_gallery.py)*

### Ranked bars paired with a timeline (`fm.compare` + `fm.trend`)

![Latency regression compare bars and trend](output/explain/latency_regression.png)

*Source: [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `fm.trend` — Change over time, dose, or scale

Direct end labels (no legend), vertical `events=` markers, missing-value gaps, shaded uncertainty `band=`, raw observations via `points=` (with optional `points_label=`), log axes (`log=`, `log_x=`), and small multiples (`facet=True`).

### ISO dates, `events=`, `baseline=`, and a missing-data gap

![ISO-date trend with retrofit event marker, baseline control, and gap](output/explain_forms/trend_dates_events.png)

```python
fm.explain(
    "The insulation retrofit cut Lab annex daily power use by 28%; the Gym stayed flat",
    fm.trend(
        dates,
        {"Lab annex": [418, 425, 412, None, 298, 304, 295, 301],
         "Library": [360, 355, 362, 358, 296, 291, 298, 294],
         "Gym (control)": [285, 290, 282, 288, 284, 279, 286, 281]},
        baseline="Gym (control)", highlight=["Lab annex", "Library"],
        events={"2026-01-25": "retrofit"},
        label="Daily electricity use", unit="kWh", x_label="Week",
        title="Both retrofitted buildings dropped immediately after Jan 25",
    ),
    note="Lab annex meter was offline during the Jan 25 switchover week.",
    source="synthetic example data",
)
```

*Source: [`explain_form_gallery.py`](explain_form_gallery.py)*

### Log-log scaling curves (`log=True, log_x=True`) with automatic power-law exponent facts

![Log-log scaling trend](output/explain_forms/trend_log_log.png)

*Source: [`explain_form_gallery.py`](explain_form_gallery.py)*

### Individual observations along ordered stages (`points=` + `points_label=`)

![Trend with individual task dots and mean lines](output/explain_forms/trend_points_tasks.png)

*Source: [`explain_form_gallery.py`](explain_form_gallery.py)*

### Raw replicates on a log dose axis (`points=`, `log_x=True`, `reference=`)

![Dose-response curves with replicate wells and shared colours](output/explain_science/dose_response.png)

*Source: [`explain_science_examples.py`](explain_science_examples.py)*

### Small multiples for more than four series (`facet=True`)

![Faceted small multiples across six regions](output/explain/regional_orders.png)

*Source: [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `fm.change` — Paired before and after

Slopegraph pairing two named states (`before`, `after`), showing absolute deltas inline and automatically wrapping in narrow columns.

![Paired benchmark accuracy slopegraph](output/explain/benchmark_gains.png)

```python
fm.explain(
    "The new model gains most where the old one was weakest: +50 points on AIME",
    fm.change(
        before, after,
        labels=("Prior", "New"), label="Accuracy", unit="%", highlight="AIME",
    ),
    source="synthetic example data",
)
```

*Source: [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `fm.distribution` — Raw observations and spread

Every observation drawn as a dot with a median (or `stat="mean"`) mark and middle-half (IQR) or ± 1 s.d. bar, plus sample counts `n=` and automatic range-separation facts.

### Log-scale fold changes with `baseline=` and `reference=`

![Log-scale gene expression distribution with baseline and reference](output/explain_forms/distribution_log.png)

```python
fm.explain(
    "Drug treatment activates p53 targets (median 2.75×) and halves proliferation genes",
    fm.distribution(
        groups,
        log=True, baseline="Housekeeping", highlight=["p53 targets", "Proliferation"],
        reference=(1.0, "no change"), label="Expression fold change", unit="×",
        title="Every p53 target rises while every proliferation gene falls",
    ),
    subtitle="Bulk RNA-seq, 24 h post-treatment; each dot is one gene",
    source="synthetic example data",
)
```

*Source: [`explain_form_gallery.py`](explain_form_gallery.py)*

### Small-n perturbation paired with mechanism (`fm.distribution` + `fm.relate`)

![Gene knockout migration distance distribution and speed-area scatter](output/explain_science/knockout.png)

*Source: [`explain_science_examples.py`](explain_science_examples.py)*

---

## `fm.relate` — Two continuous measures

Scatter plot with optional `groups=` (up to 4, directly labelled), `names=` (to call out specific points with `highlight=`), `fit=True` least-squares lines with computed `r`, `n`, and 95% slope CIs, and `log_x=`/`log_y=`.

### Grouped scatter with per-group linear fits and 95% slope CIs

![Hall-Petch yield strength vs inverse square root grain size across three alloys](output/explain_forms/relate_groups_fit.png)

```python
fm.explain(
    "All three alloys follow Hall–Petch; Cu–Zn strengthens 2.3× faster than pure Cu",
    fm.relate(
        inv_sqrt_d, yield_mpa,
        groups=alloy, fit=True, highlight="Cu–Zn",
        x_label="d⁻½ (µm⁻½)", y_label="Yield strength (MPa)", unit="MPa",
        title="Grain refinement pays off steepest in Cu–Zn (r = 0.97)",
    ),
    source="synthetic example data",
)
```

*Source: [`explain_form_gallery.py`](explain_form_gallery.py)*

### Log-log scatter with fitted power law and highlighted points (`names=`)

![Log-log allometric scaling from mouse to elephant](output/explain_forms/relate_log_allometry.png)

*Source: [`explain_form_gallery.py`](explain_form_gallery.py)*

---

## `fm.share` — Part of a whole

Sorted percentage bars (never a pie), folding smaller parts past `top=` into one muted `"Other (n)"` bar while reporting the total in the panel subtitle and combined highlighted shares in `facts`.

![Build time share bars with folded Other category](output/explain/build_time.png)

```python
fm.explain(
    "Three stages take 82% of the build: compile, integration tests and image push",
    fm.share(
        stages,
        label="build time", unit="s",
        highlight=["compile", "integration tests", "image push"], top=6,
    ),
    source="synthetic example data",
)
```

*Source: [`explain_chat_examples.py`](explain_chat_examples.py)*

---

## `fm.matrix` — Two categorical dimensions

Heat table with a number in every cell, automatic high-contrast text colour, highlighted cells/rows/columns, diverging ramps (`diverging=True`) for signed data, and em-dash (`—`) markers for missing cells.

### Sequential matrix with outlier cell highlight

![Agent task solve rate matrix with highlighted failure cell](output/explain/agent_matrix.png)

*Source: [`explain_chat_examples.py`](explain_chat_examples.py)*

### Diverging correlation matrix (`diverging=True`)

![Diverging Pearson correlation matrix across materials descriptors](output/explain_science/descriptor_correlations.png)

*Source: [`explain_science_examples.py`](explain_science_examples.py)*

### Rectangular matrix with missing (`NaN`) cells

![Evaluation matrix showing em-dash markers for missing cells](output/explain_forms/matrix_missing.png)

*Source: [`explain_form_gallery.py`](explain_form_gallery.py)*

---

## Visual styles (`style=`)

Styles change the visual surface only — never the information-design rules. Pass `style="figmint"` (default), `"bold"`, `"editorial"`, or `"sketch"` (hand-drawn for illustrative data).

| `figmint` (default) | `bold` |
| :---: | :---: |
| ![figmint style](output/explain/latency_regression.png) | ![bold style](output/explain_styles/bold/latency_regression.png) |
| **`editorial`** | **`sketch`** |
| ![editorial style](output/explain_styles/editorial/latency_regression.png) | ![sketch style](output/explain_styles/sketch/latency_regression.png) |

*All six general examples in all four styles: [`explain_style_showcase.py`](explain_style_showcase.py) → `output/explain_styles/`.*

---

## Editing returned figures and CLI

Every PNG saved by `fm.explain` embeds its normalized JSON spec. Rebuild and modify a figure without re-deriving the data:

```python
spec = fm.load("ablation.png").to_spec()
spec["style"] = "editorial"
spec["panels"][0]["highlight"] = ["no fine-tuning"]
print(fm.explain_from_spec(spec).save("ablation_v2.png", write_spec=True))
```

Or from the command line with no Python script:

```bash
figmint explain --example | figmint explain - --out latency.png
figmint explain --show-spec latency.png
figmint explain latency.png --style bold --out latency_bold.png
```

---

## Publication Figures (`fm.figure`, `fm.Plate`, `figmint run`)

Exact physical millimetre geometry, uniform sans-serif typography and math, Type 42 vector PDFs, automated CVD + grayscale proof sheets, and reproducible manuscript bundles. See [`benchmark_comparison.md`](benchmark_comparison.md) for the quantitative PDF/preflight audit.

### Before vs. After default Matplotlib

![Before vs After single-column Nature figure](output/before_after_nature.png)

*Source: [`generate_showcase.py`](generate_showcase.py)*

### One-line journal switch (*Nature* 183 mm vs. *Science* 184 mm)

![Nature vs Science one-line journal switch](output/nature_vs_science.png)

*Source: [`generate_showcase.py`](generate_showcase.py)*

### Multi-panel publication plates

| *Nature* double-column quantum phase diagram (`183 mm`) | *Science* 3-column exoplanet spectroscopy (`184 mm`) |
| :---: | :---: |
| ![Nature quantum critical dome](output/nature_quantum_critical_dome.png) | ![Science exoplanet atmosphere](output/science_exoplanet_atmosphere.png) |
| [`nature_quantum_critical_dome.py`](nature_quantum_critical_dome.py) | [`science_exoplanet_atmosphere.py`](science_exoplanet_atmosphere.py) |
| **NeurIPS Tufte scaling + slopegraph + sparklines (`139.7 mm`)** | **Cell Press lineage bifurcation (`174 mm`)** |
| ![NeurIPS Tufte plate](output/neurips_frontier_tufte/preview.png) | ![Cell lineage bifurcation](output/cell_lineage_bifurcation/preview.png) |
| [`neurips_frontier_tufte.py`](neurips_frontier_tufte.py) | [`cell_lineage_bifurcation.py`](cell_lineage_bifurcation.py) |

### Automated CVD + grayscale proof sheet (`plate.bundle(...)`)

![Nature 4-panel plate CVD and grayscale proof sheet](output/example2_nature_proof.png)

*More publication plates in this folder: [`masterpiece_1_chaos.py`](masterpiece_1_chaos.py), [`masterpiece_2_omics.py`](masterpiece_2_omics.py), [`masterpiece_3_climate.py`](masterpiece_3_climate.py), [`neurips_frontier_scaling.py`](neurips_frontier_scaling.py).*
