# mintfig Publication Figures Reference

Use this workflow when generating manuscript or report plates for *Nature*, *Science*, *Science Advances*, *Cell*, PNAS, NeurIPS, or screen review.

`mint.Plate` and `mint.figure` are top-level; every other publication tool (styling, annotation primitives, journal specs, export, preflight, palettes) lives in `mint.pub`. PDF checks (`--bundle`, `mintfig check`, `mint.pub.preflight_pdf`) need `pip install "mintfig[pub]"`.

## Standard Agent Workflow

1. Write a self-contained Python plotting script (`plot.py`) following the **Script Contract** below.
2. Run preflight + export bundle in one command:
   ```bash
   mintfig run plot.py --journal nature --bundle out/ --json
   ```
   (Supports `--journal nature|science|science_advances|cell|pnas|neurips|screen` and optional `--width`.)
3. Inspect the JSON output (`schema_version: "0.2"`):
   - Exit `0` (`ok: true`): passes all deterministic journal rules. Review any clarity `warning` items (`color_separation`, `clarity_metadata`), then show `out/preview.png` (and `out/proof.png` for CVD/print verification).
   - Exit `1` (`stage: "preflight"`): read `issues` where `severity == "error"`, apply each `fix_hint` using `panel`, `panels`, `elements`, and `element_locations`, and re-run.
   - Exit `2` (`stage: "contract"` or `"runtime"`): fix the contract or exception using `error` and `fix_hint`, then re-run.
4. **2-Loop Repair Cap:** perform at most 2 repair loops. If an error remains, stop, report remaining `issues`, and show `out/preview.png`.

## Script Contract

`mintfig run` discovers your figure in priority order:
1. Module-level `def build(...) -> mint.Plate | matplotlib.figure.Figure` (optionally accepting `journal` and/or `width`).
2. Module-level `plate` (`mintfig.Plate`) or `fig` (`matplotlib.figure.Figure`).

Optional module-level metadata flowing into `figure.tex` and `figure.json`:
- `CAPTION: str` — manuscript caption
- `LABEL: str` — LaTeX `\label{...}` (default `"fig:fig1"`)
- `TAKEAWAY: str` — one-sentence human takeaway
- `PANEL_NOTES: dict[str, str]` — one-line reading per panel

```python
import numpy as np
import mintfig as mint


def build(journal: str = "nature") -> mint.Plate:
    plate = mint.Plate(journal=journal, width="double", height_mm=105.0, layout=(1, 2))
    x = np.linspace(0, 10, 200)
    plate["a"].plot(x, np.exp(-x / 3.0), label="Control")
    plate["a"].plot(x, np.exp(-x / 6.0), label="Treated")
    plate["a"].set_xlabel("Time (h)")
    plate["a"].set_ylabel(r"Signal ($\mu\mathrm{M}$)")
    mint.pub.direct_labels(plate["a"])

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

- **Small multiples over spaghetti:** for `> 4` curves, split into shared-axis small multiples with `mint.pub.ghost_context(...)`.
- **High-density comparative forms:** `mint.pub.slopegraph(...)`, `mint.pub.sparkline(...)`, `mint.pub.tufte_boxplot(...)`.
- **Maximize data-ink & trim spines:** `mint.pub.range_frame(ax, rug=True)`, unboxed legends (`frameon=False`), `mint.pub.direct_labels(ax)`, and `mint.pub.emphasize(ax, keep=...)`.
- **Micro/macro layering:** keep large fills and CI ribbons pale (`alpha <= 0.14`); reserve saturated ink for focal findings.
- **Graphical integrity:** start positive bar charts at zero; scale bubble markers by area (`s ∝ value`); always show uncertainty and sample size `n`.

## Publication Best Practices

- Never use rainbow/jet colormaps (`jet`, `rainbow`, `hsv`, `gist_rainbow`, `nipy_spectral`, `prism`, `flag`); use perceptual colormaps (`viridis`, `magma`, `cividis`, `inferno`, `mintfig_navy`, `mintfig_teal`, `mintfig_div`).
- Never pass `bbox_inches="tight"` — `mintfig` locks exact millimeter MediaBox dimensions via `constrained_layout`.
- Wrap mathtext units in `\mathrm{...}` (e.g. `r"$\mathrm{\mu m}$"`).
- Bundle outputs in `out/`: `figure.pdf` (Type 42 editable vector), `figure.svg`, `preview.png`, `proof.png`, `figure.tex`, `figure.json`, `reproduce.py`, and `report.json`.
