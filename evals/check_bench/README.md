# Wild-50 `mint.check` Verification Corpus

A deterministic, zero-network benchmark of 50 real-world Matplotlib and
Seaborn-idiom figures for auditing `mint.check` false-positive rate and defect
recall.

## Design

- **Zero extra dependencies**: Uses Matplotlib + NumPy only (no Seaborn
  required in CI), while constructing exact Seaborn artist hierarchies:
  `QuadMesh` heatmaps + colorbars, `PolyCollection` `fill_between` CI bands,
  contiguous-edge `BarContainer` histograms (count & density), `patch_artist`
  and classic boxplots, violinplots, grouped / horizontal / stacked bars,
  `datetime.date` multi-line series, log-log scaling curves, scatter + OLS fit,
  1×2 and 2×2 multi-panel subplots, dark theme, and framed legends.
- **25 Clean figures** (`expected_ship=True`): Legible, accurately labeled
  figures with realistic ML and science headlines (model names like
  `Llama-3.1 8B`, `GPT-4`, `GPT-5`, `ResNet-50`, precision tags `FP16`, `INT4`,
  `Q4_K_M`, version/ranking tokens `v2.3`, `top-5`, sample descriptors
  `5 seeds`, `3 replicates`, `10k steps`, `95% CI`, `p < 0.05`, `p = 0.01`,
  calendar years `2026`, and unit-scale conversions `0.08 s` ↔ `80 ms`,
  `4500` ↔ `4.5k`, `0.08` ↔ `8%`).
- **25 Defective figures** (`expected_ship=False`, labeled ground-truth rules):
  - `claim_number_mismatch` (5): bars, lines, `QuadMesh` heatmap, boxplot, histogram
  - `bar_baseline_nonzero` (3): vertical, horizontal, grouped bars
  - `text_too_small` (4): oversized figure at 700 px chat width, explicit 6 pt
    fonts, 450 px narrow width, wide 1×3 multi-panel at 700 px
  - `text_overlaps` (3): scatter annotations, 10 unrotated x-ticks, line-end labels
  - `text_struck_by_line` (3): data line, dashed reference line, frameless legend
  - `rainbow_colormap` (3): `imshow(..., cmap="jet")`, `pcolormesh(..., cmap="hsv")`,
    `scatter(..., cmap="rainbow")`
  - `text_malformed` (3): doubled `%%`, raw `nan`, ASCII hyphen `-` as minus sign
  - `text_clipped` (1): figure text extending past the right canvas edge

## Targets

| Metric | Target |
| --- | --- |
| Clean false-positive rate | `< 2%` (0 / 25) |
| Defect catch rate (`ship=False`) | `> 90%` (`>= 23 / 25`) |
| Exact-rule recall | `> 90%` (`>= 23 / 25`) |

## Usage

Run the evaluation harness to regenerate `REPORT.md` and `report.json`:

```bash
PYTHONPATH=src MPLCONFIGDIR=/tmp/mpl-mintfig python evals/check_bench/run_wild_eval.py
```

Run the pytest verification suite:

```bash
PYTHONPATH=src MPLCONFIGDIR=/tmp/mpl-mintfig pytest tests/test_figcheck_wild.py
```

## Files

- `corpus.py` — 50 deterministic `WildCase` builders (`WILD_50`)
- `run_wild_eval.py` — Evaluation runner and Markdown/JSON report generator
- `REPORT.md` — Latest verification report with FP/missed-defect tables
- `report.json` — Machine-readable evaluation output
