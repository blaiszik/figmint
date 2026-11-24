# `figmint` v0.2 Empirical Validation Report (35-Script Gate)

This report documents the empirical validation gate for `figmint` v0.2 (`figmint run --json`, high-precision `preflight.py`, panel-attributed `fix_hint`s, strict script contract, and `<= 2`-loop repair cap).

All runs executed the real CLI subprocess (`.venv/bin/figmint run <script> --journal <j> --json`) via [`evals/run_eval.py`](run_eval.py). Raw telemetry is recorded in [`evals/output/eval_results.json`](output/eval_results.json).

---

## 1. Headline Metrics

| Evaluation Slice | Scripts | Metric | Result | Target |
| :--- | :---: | :--- | :---: | :---: |
| **Control Set** (10 already-clean `figmint` scripts) | 10 | False-positive **errors** | **`0 / 10` (0.0%)** | `0 / 10` |
| **Control Set** (10 already-clean `figmint` scripts) | 10 | False-positive **warnings** | **`0 / 10` (0.0%)** | `0 / 10` |
| **Messy Set** (25 shot-#0 realistic scripts) | 25 | **Loop 0** error-free / zero-warn clean | `4 / 25` (16%) / `0 / 25` (0%) | — |
| **Messy Set** (<= 2-loop generic JSON repair) | 25 | **Loop 1** error-free / zero-warn clean | **`24 / 25` (96.0%)** / **`23 / 25` (92.0%)** | — |
| **Messy Set** (<= 2-loop generic JSON repair) | 25 | **Loop 2** error-free / zero-warn clean | **`25 / 25` (100.0%)** / **`24 / 25` (96.0%)** | **>= 90%** |

> **Methodology note:** The repair harness in [`evals/run_eval.py`](run_eval.py) contains **zero per-filename hardcoding**. Every edit is dispatched generically from `stage`, `issues[].rule`, `issues[].severity`, `issues[].elements`, and `issues[].fix_hint` in the `schema_version: "0.2"` JSON output, with a strict cap of **2 repair loops**.

---

## 2. Control Set Results (10 Clean Scripts — 0% False Positives)

| Script | Journal | Contract | Measured Size (mm) | Errors | Warnings | Result |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| `clean_01_nature_single_dose.py` | `nature` | `def build()` | `88.9 × 63.8` | 0 | 0 | **PASS** |
| `clean_02_nature_double_2x2.py` | `nature` | `def build()` | `182.9 × 111.9` | 0 | 0 | **PASS** |
| `clean_03_nature_mid_mosaic.py` | `nature` | `def build()` | `119.9 × 82.0` | 0 | 0 | **PASS** |
| `clean_04_science_1col_spectra.py` | `science` | `def build(journal)` | `54.9 × 50.0` | 0 | 0 | **PASS** |
| `clean_05_science_2col_volcano.py` | `science` | `def build()` | `119.9 × 75.9` | 0 | 0 | **PASS** |
| `clean_06_science_3col_climate.py` | `science` | `def build()` | `183.9 × 67.9` | 0 | 0 | **PASS** |
| `clean_07_sciadv_double_roc.py` | `science_advances` | `def build()` | `174.9 × 74.0` | 0 | 0 | **PASS** |
| `clean_08_nature_umap_25k.py` | `nature` | `def build()` | `88.9 × 72.0` | 0 | 0 | **PASS** |
| `clean_09_nature_confocal_scalebar.py` | `nature` | `def build()` | `88.9 × 72.0` | 0 | 0 | **PASS** |
| `clean_10_nature_box_sig.py` | `nature` | top-level `plate` | `88.9 × 67.9` | 0 | 0 | **PASS** |

---

## 3. Messy Set Results (25 Realistic Shot-#0 Scripts)

| Script | Journal | Loop 0 Issues (Errors / Warnings) | Loops | Final Status | Final Size (mm) |
| :--- | :--- | :--- | :---: | :---: | :---: |
| `messy_01_default_scatter.py` | `nature` | `dimensions`, `warn:font_sizes`, `warn:vector_fonts` | 1 | **PASS** (0E / 0W) | `182.9 × 137.2` |
| `messy_02_wide_line_kinetics.py` | `nature` | `dimensions`, `warn:font_sizes`, `warn:vector_fonts` | 1 | **PASS** (0E / 0W) | `182.9 × 109.7` |
| `messy_03_bar_default_figsize.py` | `science` | `dimensions`, `warn:font_sizes`, `warn:vector_fonts` | 1 | **PASS** (0E / 0W) | `183.9 × 131.2` |
| `messy_04_violin_oversized_text.py` | `nature` | `dimensions`, `warn:font_sizes`, `warn:vector_fonts` | 1 | **PASS** (0E / 0W) | `119.9 × 74.8` |
| `messy_05_volcano_jet_cmap.py` | `nature` | `colormaps` (`jet`) | 1 | **PASS** (0E / 0W) | `88.9 × 65.9` |
| `messy_06_heatmap_rainbow_cmap.py` | `nature` | `colormaps` (`rainbow`) | 1 | **PASS** (0E / 0W) | `88.9 × 69.9` |
| `messy_07_phase_hsv_cmap.py` | `science` | `colormaps` (`hsv`) | 1 | **PASS** (0E / 0W) | `119.9 × 75.9` |
| `messy_08_survival_tiny_text.py` | `nature` | `font_sizes` (`3.5 pt`) | 1 | **PASS** (0E / 0W) | `88.9 × 65.9` |
| `messy_09_residuals_tiny_ticks.py` | `science` | `font_sizes` (`4.2 pt < 6.0 pt`) | 1 | **PASS** (0E / 0W) | `119.9 × 72.0` |
| `messy_10_roc_tiny_auc.py` | `nature` | `font_sizes` (`3.8 pt`) | 1 | **PASS** (0E / 0W) | `88.9 × 65.9` |
| `messy_11_bar_clipped_xlabel.py` | `nature` | `canvas_clipping`, `warn:vector_fonts` | 2 | **PASS** (0E / 1W*) | `88.9 × 57.9` |
| `messy_12_heatmap_clipped_title.py` | `nature` | `canvas_clipping` | 1 | **PASS** (0E / 0W) | `88.9 × 63.8` |
| `messy_13_scatter_colliding_labels.py` | `nature` | `text_overlaps` (`STAT3` vs `SOCS3`) | 1 | **PASS** (0E / 0W) | `88.9 × 67.9` |
| `messy_14_line_overlapping_annotations.py` | `nature` | `text_overlaps` (`WT peak` vs `KO peak`) | 1 | **PASS** (0E / 0W) | `88.9 × 65.9` |
| `messy_15_cramped_xticks_overlap.py` | `science` | `text_overlaps` (6 cramped ticks on 55 mm) | 2 | **PASS** (0E / 0W) | `54.9 × 55.9` |
| `messy_16_legend_collides_annotation.py` | `nature` | `warn:text_overlaps` (legend vs text) | 1 | **PASS** (0E / 0W) | `88.9 × 65.9` |
| `messy_17_serif_times_override.py` | `nature` | `warn:font_family` | 1 | **PASS** (0E / 0W) | `88.9 × 63.8` |
| `messy_18_cm_serif_mathtext.py` | `science` | `warn:font_sizes`, `warn:font_family`, `warn:vector_fonts` | 1 | **PASS** (0E / 0W) | `119.9 × 75.9` |
| `messy_19_hairline_strokes.py` | `nature` | `warn:hairline_strokes` (`0.1 pt`) | 1 | **PASS** (0E / 0W) | `88.9 × 63.8` |
| `messy_20_oversized_height.py` | `nature` | `dimensions` (`260 mm > 247 mm`) | 1 | **PASS** (0E / 0W) | `182.9 × 154.9` |
| `messy_21_contract_missing_export.py` | `nature` | `script_contract` (exit code 2) | 1 | **PASS** (0E / 0W) | `88.9 × 63.8` |
| `messy_22_contract_local_only.py` | `science` | `script_contract` (exit code 2) | 1 | **PASS** (0E / 0W) | `119.9 × 74.0` |
| `messy_23_compound_width_jet_tiny.py` | `nature` | `dimensions`, `font_sizes`, `colormaps`, `warn:vector_fonts` | 1 | **PASS** (0E / 0W) | `182.9 × 121.9` |
| `messy_24_compound_multipanel_mess.py` | `nature` | `dimensions`, `font_sizes`, `text_overlaps`, `colormaps`, `warn:vector_fonts` | 1 | **PASS** (0E / 0W) | `182.9 × 133.1` |
| `messy_25_compound_science_clip_overlap_jet.py` | `science` | `dimensions`, `text_overlaps`, `canvas_clipping`, `colormaps`, `warn:font_sizes`, `warn:vector_fonts` | 1 | **PASS** (0E / 0W) | `119.9 × 74.8` |

---

## 4. Edge Cases Discovered & Honest Findings

1. **`with fm.use(...)` scoping warning (`messy_11_bar_clipped_xlabel.py`, marked `1W*` above):**
   - `messy_11` creates its figure inside `with fm.use("nature"):` and returns `fig` after exiting the context manager. Because `preflight_figure` checks live `plt.rcParams["pdf.fonttype"]`, it emits a benign `vector_fonts` warning once `fm.use()` exits — even though `bundle_figure` / `save_figure` still exports `figure.pdf` with `pdf.fonttype = 42` and **0 Type 3 fonts**. Using `fm.Plate(...)` or `fm.apply(journal)` avoids this completely.
2. **Axis-aligned bounding boxes for tilted ticks on narrow 55 mm Science 1-col figures (`messy_15`):**
   - Rotating 6 long category labels (`Condition_01`..`Condition_06`) by 40° on a 55 mm wide plot still triggered `text_overlaps` at Loop 1 because Matplotlib's `get_window_extent()` returns axis-aligned rectangles. Escalating to vertical `rotation=90, ha="center"` on Loop 2 eliminated all overlaps cleanly and produced a crisp, legible narrow-column bar chart.
3. **High-precision severity split validated:**
   - The 4 scripts with warning-only flaws (`messy_16` moderate overlap, `messy_17` serif override, `messy_18` DejaVu Serif/Type 3 rcParams, `messy_19` hairline strokes) correctly exited `0` (`ok=True`) while emitting actionable `warning` issues that cleanly resolved to 0 warnings in 1 loop.
   - Both contract-violation scripts (`messy_21`, `messy_22`) cleanly exited `2` (`stage="contract"`) with exact `fix_hint` guidance and passed at Loop 1.
   - All 3 compound multi-bug scripts (`messy_23`, `messy_24`, `messy_25` — 3 to 6 simultaneous issues each) resolved all errors and warnings in a **single repair loop**.

---

## 5. Visual Audit Notes

Visual inspection of the 3×3 repaired contact sheet ([`evals/output/eval_contact_sheet.png`](output/eval_contact_sheet.png)) and spot-checked individual bundles (`messy_25`) confirms that repairs genuinely improved visual quality rather than gaming the linter:
- `messy_01_default_scatter`: stock Matplotlib spines, grid, and oversized fonts replaced by clean NPG styling at exact double-column `182.9 × 137.2 mm`.
- `messy_05` & `messy_06`: banned `jet` and `rainbow` colormaps replaced with perceptual `viridis` with crisp styled colorbars.
- `messy_08`: `3.5 pt` survival annotations raised to legible `6.0 pt` with clean separation.
- `messy_11`: clipped bottom axis title recovered completely via `layout="constrained"`.
- `messy_13`, `messy_16`, `messy_24`, `messy_25`: colliding annotations (`STAT3`/`SOCS3`, `Cluster A`/`Cluster B`, `State Alpha`/`State Beta`) cleanly separated and colliding legends relocated into open whitespace.
- `messy_15`: 6 cramped Science 55 mm x-ticks rotated cleanly to 90° with zero overlap or bottom clipping.
