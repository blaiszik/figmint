# Wild-50 `mint.check` Verification Report

- **Git SHA**: `bd4ed55`
- **Runtime**: 2.54s across 50 figures

## Headline Metrics

| Metric | Result | Target | Status |
| --- | --- | --- | --- |
| Clean False-Positive Rate | 9/25 (36.0%) | < 2% (0/25) | FAIL |
| Defect Catch Rate (`ship=False`) | 25/25 (100.0%) | > 90% (>= 23/25) | PASS |
| Exact-Rule Recall | 25/25 (100.0%) | > 90% (>= 23/25) | PASS |
| Clean with Non-Blocking Warnings | 0/25 | 0 (advisory) | INFO |

## Breakdown by Defect Category

| Defect Rule | Total | Caught (`ship=False`) | Exact-Rule Match | Recall |
| --- | ---: | ---: | ---: | ---: |
| `bar_baseline_nonzero` | 3 | 3 | 3 | 100% |
| `claim_number_mismatch` | 5 | 5 | 5 | 100% |
| `rainbow_colormap` | 3 | 3 | 3 | 100% |
| `text_clipped` | 1 | 1 | 1 | 100% |
| `text_malformed` | 3 | 3 | 3 | 100% |
| `text_overlaps` | 3 | 3 | 3 | 100% |
| `text_struck_by_line` | 3 | 3 | 3 | 100% |
| `text_too_small` | 4 | 4 | 4 | 100% |

## Breakdown by Artist Category

| Artist Category | Total | Clean Pass | Clean FP | Defect Caught | Defect Exact Rule |
| --- | ---: | ---: | ---: | ---: | ---: |
| `bars_grouped` | 8 | 1/1 | 0 | 7/7 | 7/7 |
| `bars_horizontal` | 3 | 2/2 | 0 | 1/1 | 1/1 |
| `bars_stacked` | 1 | 1/1 | 0 | 0/0 | 0/0 |
| `boxplot` | 3 | 2/2 | 0 | 1/1 | 1/1 |
| `ci_band` | 2 | 1/2 | 1 | 0/0 | 0/0 |
| `dark_theme` | 1 | 1/1 | 0 | 0/0 | 0/0 |
| `errorbar` | 1 | 0/1 | 1 | 0/0 | 0/0 |
| `framed_legend` | 2 | 1/1 | 0 | 1/1 | 1/1 |
| `headline_tokens` | 3 | 2/3 | 1 | 0/0 | 0/0 |
| `histogram` | 3 | 0/2 | 2 | 1/1 | 1/1 |
| `image_imshow` | 2 | 1/1 | 0 | 1/1 | 1/1 |
| `lines_dates` | 9 | 1/1 | 0 | 8/8 | 8/8 |
| `log_log` | 1 | 1/1 | 0 | 0/0 | 0/0 |
| `multi_panel` | 3 | 2/2 | 0 | 1/1 | 1/1 |
| `quadmesh` | 4 | 0/2 | 2 | 2/2 | 2/2 |
| `scatter_ols` | 3 | 0/1 | 1 | 2/2 | 2/2 |
| `violinplot` | 1 | 0/1 | 1 | 0/0 | 0/0 |

## False Positives on Clean Cases

| Case ID | Artist | Triggered Rules | Unmatched Tokens / Detail |
| --- | --- | --- | --- |
| `clean_01_quadmesh_heatmap_colorbar` | `quadmesh` | `claim_number_mismatch` | `0.92` |
| `clean_02_quadmesh_diverging_ratio` | `quadmesh` | `claim_number_mismatch` | `4x`; `48` |
| `clean_04_ci_band_upper_bound` | `ci_band` | `claim_number_mismatch` | `94%` (nearest: end (Tuned (±1 s.d., n = 8)) = 88) |
| `clean_05_hist_counts` | `histogram` | `claim_number_mismatch` | `40` (nearest: 37.5 vs 52.5: 66 − 21 = 45) |
| `clean_06_hist_density` | `histogram` | `claim_number_mismatch` | `18` |
| `clean_09_violinplot_medians` | `violinplot` | `claim_number_mismatch` | `65` |
| `clean_15_scatter_ols_regplot` | `scatter_ols` | `claim_number_mismatch` | `0.05` |
| `clean_20_unit_scale_seconds_to_ms` | `headline_tokens` | `claim_number_mismatch` | `0.01` (nearest: Pruned vs Llama-3.1 70B: 0.12 − 0.08 = 0.04) |
| `clean_23_errorbar_categorical` | `errorbar` | `claim_number_mismatch` | `0.05` |

## Missed Defects / Wrong Rule on Defective Cases

None (25/25 exact-rule matches).

## Artist Extraction Diagnostics

| Case ID | Artist | Observation |
| --- | --- | --- |
| `clean_01_quadmesh_heatmap_colorbar` | `quadmesh` | QuadMesh not extracted (`panel_kinds=['empty', 'empty']`) |
| `clean_01_quadmesh_heatmap_colorbar` | `quadmesh` | Colorbar included as extra panel (`panel_kinds=['empty', 'empty']`) |
| `clean_02_quadmesh_diverging_ratio` | `quadmesh` | QuadMesh not extracted (`panel_kinds=['empty', 'empty']`) |
| `clean_02_quadmesh_diverging_ratio` | `quadmesh` | Colorbar included as extra panel (`panel_kinds=['empty', 'empty']`) |
| `clean_05_hist_counts` | `histogram` | Histogram read as categorical `bars` (`panel_kinds=['bars']`) |
| `clean_06_hist_density` | `histogram` | Histogram read as categorical `bars` (`panel_kinds=['bars']`) |
| `clean_07_boxplot_patch_artist` | `boxplot` | Boxplot geometry read as `lines` (`panel_kinds=['lines']`) |
| `clean_08_boxplot_classic_lines` | `boxplot` | Boxplot geometry read as `lines` (`panel_kinds=['lines']`) |
| `clean_09_violinplot_medians` | `violinplot` | Violinplot not extracted (`panel_kinds=['empty']`) |
| `clean_24_imshow_cividis_colorbar` | `image_imshow` | Colorbar included as extra panel (`panel_kinds=['image', 'empty']`) |
| `defect_03_claim_mismatch_quadmesh` | `quadmesh` | QuadMesh not extracted (`panel_kinds=['empty', 'empty']`) |
| `defect_03_claim_mismatch_quadmesh` | `quadmesh` | Colorbar included as extra panel (`panel_kinds=['empty', 'empty']`) |
| `defect_04_claim_mismatch_boxplot` | `boxplot` | Boxplot geometry read as `lines` (`panel_kinds=['lines']`) |
| `defect_05_claim_mismatch_hist` | `histogram` | Histogram read as categorical `bars` (`panel_kinds=['bars']`) |
| `defect_19_rainbow_imshow_jet` | `image_imshow` | Colorbar included as extra panel (`panel_kinds=['image', 'empty']`) |
| `defect_20_rainbow_quadmesh_hsv` | `quadmesh` | QuadMesh not extracted (`panel_kinds=['empty', 'empty']`) |
| `defect_20_rainbow_quadmesh_hsv` | `quadmesh` | Colorbar included as extra panel (`panel_kinds=['empty', 'empty']`) |
| `defect_21_rainbow_scatter_rainbow` | `scatter_ols` | Colorbar included as extra panel (`panel_kinds=['scatter', 'empty']`) |

## Full Case Matrix

| Case ID | Split | Artist | Expected | Actual `ship` | Expected Rules | Actual Rules | ms |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| `clean_01_quadmesh_heatmap_colorbar` | clean | `quadmesh` | FAIL | `False` | - | claim_number_mismatch | 66 |
| `clean_02_quadmesh_diverging_ratio` | clean | `quadmesh` | FAIL | `False` | - | claim_number_mismatch | 50 |
| `clean_03_ci_band_fill_between` | clean | `ci_band` | PASS | `True` | - | - | 54 |
| `clean_04_ci_band_upper_bound` | clean | `ci_band` | FAIL | `False` | - | claim_number_mismatch | 52 |
| `clean_05_hist_counts` | clean | `histogram` | FAIL | `False` | - | claim_number_mismatch | 51 |
| `clean_06_hist_density` | clean | `histogram` | FAIL | `False` | - | claim_number_mismatch | 54 |
| `clean_07_boxplot_patch_artist` | clean | `boxplot` | PASS | `True` | - | - | 41 |
| `clean_08_boxplot_classic_lines` | clean | `boxplot` | PASS | `True` | - | - | 41 |
| `clean_09_violinplot_medians` | clean | `violinplot` | FAIL | `False` | - | claim_number_mismatch | 38 |
| `clean_10_grouped_bars_ml_models` | clean | `bars_grouped` | PASS | `True` | - | - | 42 |
| `clean_11_horizontal_bars_precision` | clean | `bars_horizontal` | PASS | `True` | - | - | 31 |
| `clean_12_stacked_bars_shares` | clean | `bars_stacked` | PASS | `True` | - | - | 41 |
| `clean_13_multiline_date_series` | clean | `lines_dates` | PASS | `True` | - | - | 63 |
| `clean_14_log_log_scaling` | clean | `log_log` | PASS | `True` | - | - | 129 |
| `clean_15_scatter_ols_regplot` | clean | `scatter_ols` | FAIL | `False` | - | claim_number_mismatch | 57 |
| `clean_16_multipanel_2x1` | clean | `multi_panel` | PASS | `True` | - | - | 63 |
| `clean_17_multipanel_2x2_grid` | clean | `multi_panel` | PASS | `True` | - | - | 144 |
| `clean_18_dark_theme_framed_legend` | clean | `dark_theme` | PASS | `True` | - | - | 52 |
| `clean_19_framed_legend_over_lines` | clean | `framed_legend` | PASS | `True` | - | - | 50 |
| `clean_20_unit_scale_seconds_to_ms` | clean | `headline_tokens` | FAIL | `False` | - | claim_number_mismatch | 33 |
| `clean_21_unit_scale_thousands_k` | clean | `headline_tokens` | PASS | `True` | - | - | 34 |
| `clean_22_unit_scale_fraction_to_pct` | clean | `headline_tokens` | PASS | `True` | - | - | 30 |
| `clean_23_errorbar_categorical` | clean | `errorbar` | FAIL | `False` | - | claim_number_mismatch | 36 |
| `clean_24_imshow_cividis_colorbar` | clean | `image_imshow` | PASS | `True` | - | - | 52 |
| `clean_25_negative_values_unicode_minus` | clean | `bars_horizontal` | PASS | `True` | - | - | 38 |
| `defect_01_claim_mismatch_bars` | defective | `bars_grouped` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 47 |
| `defect_02_claim_mismatch_lines` | defective | `lines_dates` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 44 |
| `defect_03_claim_mismatch_quadmesh` | defective | `quadmesh` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 40 |
| `defect_04_claim_mismatch_boxplot` | defective | `boxplot` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 41 |
| `defect_05_claim_mismatch_hist` | defective | `histogram` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 41 |
| `defect_06_truncated_vbar` | defective | `bars_grouped` | PASS | `False` | bar_baseline_nonzero | bar_baseline_nonzero | 40 |
| `defect_07_truncated_hbar` | defective | `bars_horizontal` | PASS | `False` | bar_baseline_nonzero | bar_baseline_nonzero | 30 |
| `defect_08_truncated_grouped_bars` | defective | `bars_grouped` | PASS | `False` | bar_baseline_nonzero | bar_baseline_nonzero | 39 |
| `defect_09_tiny_text_wide_chat` | defective | `bars_grouped` | PASS | `False` | text_too_small | text_too_small | 44 |
| `defect_10_tiny_text_explicit_small_font` | defective | `lines_dates` | PASS | `False` | text_too_small | text_too_small | 50 |
| `defect_11_tiny_text_narrow_450` | defective | `lines_dates` | PASS | `False` | text_too_small | text_too_small | 41 |
| `defect_12_tiny_text_multipanel_chat` | defective | `multi_panel` | PASS | `False` | text_too_small | text_too_small | 133 |
| `defect_13_overlapping_annotations` | defective | `scatter_ols` | PASS | `False` | text_overlaps | text_overlaps | 47 |
| `defect_14_overlapping_xticks` | defective | `bars_grouped` | PASS | `False` | text_overlaps | text_overlaps | 56 |
| `defect_15_overlapping_line_end_labels` | defective | `lines_dates` | PASS | `False` | text_overlaps | text_overlaps | 46 |
| `defect_16_struck_by_data_line` | defective | `lines_dates` | PASS | `False` | text_struck_by_line | text_struck_by_line | 48 |
| `defect_17_struck_by_reference_line` | defective | `lines_dates` | PASS | `False` | text_struck_by_line | text_struck_by_line | 50 |
| `defect_18_struck_frameless_legend` | defective | `framed_legend` | PASS | `False` | text_struck_by_line | text_struck_by_line | 45 |
| `defect_19_rainbow_imshow_jet` | defective | `image_imshow` | PASS | `False` | rainbow_colormap | rainbow_colormap | 52 |
| `defect_20_rainbow_quadmesh_hsv` | defective | `quadmesh` | PASS | `False` | rainbow_colormap | rainbow_colormap, claim_number_mismatch | 44 |
| `defect_21_rainbow_scatter_rainbow` | defective | `scatter_ols` | PASS | `False` | rainbow_colormap | rainbow_colormap | 56 |
| `defect_22_malformed_doubled_pct` | defective | `bars_grouped` | PASS | `False` | text_malformed | text_malformed | 36 |
| `defect_23_malformed_nan_junk` | defective | `lines_dates` | PASS | `False` | text_malformed | text_malformed | 45 |
| `defect_24_malformed_ascii_minus` | defective | `bars_grouped` | PASS | `False` | text_malformed | text_malformed | 33 |
| `defect_25_clipped_right_edge` | defective | `lines_dates` | PASS | `False` | text_clipped | text_clipped | 27 |
