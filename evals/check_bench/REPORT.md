# Wild-50 `mint.check` Verification Report

- **Git SHA**: `06bea62`
- **Runtime**: 2.48s across 50 figures

## Headline Metrics

| Metric | Result | Target | Status |
| --- | --- | --- | --- |
| Clean False-Positive Rate | 0/25 (0.0%) | < 2% (0/25) | PASS |
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
| `ci_band` | 2 | 2/2 | 0 | 0/0 | 0/0 |
| `dark_theme` | 1 | 1/1 | 0 | 0/0 | 0/0 |
| `errorbar` | 1 | 1/1 | 0 | 0/0 | 0/0 |
| `framed_legend` | 2 | 1/1 | 0 | 1/1 | 1/1 |
| `headline_tokens` | 3 | 3/3 | 0 | 0/0 | 0/0 |
| `histogram` | 3 | 2/2 | 0 | 1/1 | 1/1 |
| `image_imshow` | 2 | 1/1 | 0 | 1/1 | 1/1 |
| `lines_dates` | 9 | 1/1 | 0 | 8/8 | 8/8 |
| `log_log` | 1 | 1/1 | 0 | 0/0 | 0/0 |
| `multi_panel` | 3 | 2/2 | 0 | 1/1 | 1/1 |
| `quadmesh` | 4 | 2/2 | 0 | 2/2 | 2/2 |
| `scatter_ols` | 3 | 1/1 | 0 | 2/2 | 2/2 |
| `violinplot` | 1 | 1/1 | 0 | 0/0 | 0/0 |

## False Positives on Clean Cases

None (0/25 false positives).

## Missed Defects / Wrong Rule on Defective Cases

None (25/25 exact-rule matches).

## Full Case Matrix

| Case ID | Split | Artist | Expected | Actual `ship` | Expected Rules | Actual Rules | ms |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| `clean_01_quadmesh_heatmap_colorbar` | clean | `quadmesh` | PASS | `True` | - | - | 79 |
| `clean_02_quadmesh_diverging_ratio` | clean | `quadmesh` | PASS | `True` | - | - | 52 |
| `clean_03_ci_band_fill_between` | clean | `ci_band` | PASS | `True` | - | - | 52 |
| `clean_04_ci_band_upper_bound` | clean | `ci_band` | PASS | `True` | - | - | 50 |
| `clean_05_hist_counts` | clean | `histogram` | PASS | `True` | - | - | 58 |
| `clean_06_hist_density` | clean | `histogram` | PASS | `True` | - | - | 50 |
| `clean_07_boxplot_patch_artist` | clean | `boxplot` | PASS | `True` | - | - | 40 |
| `clean_08_boxplot_classic_lines` | clean | `boxplot` | PASS | `True` | - | - | 35 |
| `clean_09_violinplot_medians` | clean | `violinplot` | PASS | `True` | - | - | 36 |
| `clean_10_grouped_bars_ml_models` | clean | `bars_grouped` | PASS | `True` | - | - | 39 |
| `clean_11_horizontal_bars_precision` | clean | `bars_horizontal` | PASS | `True` | - | - | 29 |
| `clean_12_stacked_bars_shares` | clean | `bars_stacked` | PASS | `True` | - | - | 41 |
| `clean_13_multiline_date_series` | clean | `lines_dates` | PASS | `True` | - | - | 60 |
| `clean_14_log_log_scaling` | clean | `log_log` | PASS | `True` | - | - | 132 |
| `clean_15_scatter_ols_regplot` | clean | `scatter_ols` | PASS | `True` | - | - | 55 |
| `clean_16_multipanel_2x1` | clean | `multi_panel` | PASS | `True` | - | - | 64 |
| `clean_17_multipanel_2x2_grid` | clean | `multi_panel` | PASS | `True` | - | - | 142 |
| `clean_18_dark_theme_framed_legend` | clean | `dark_theme` | PASS | `True` | - | - | 53 |
| `clean_19_framed_legend_over_lines` | clean | `framed_legend` | PASS | `True` | - | - | 51 |
| `clean_20_unit_scale_seconds_to_ms` | clean | `headline_tokens` | PASS | `True` | - | - | 33 |
| `clean_21_unit_scale_thousands_k` | clean | `headline_tokens` | PASS | `True` | - | - | 33 |
| `clean_22_unit_scale_fraction_to_pct` | clean | `headline_tokens` | PASS | `True` | - | - | 30 |
| `clean_23_errorbar_categorical` | clean | `errorbar` | PASS | `True` | - | - | 35 |
| `clean_24_imshow_cividis_colorbar` | clean | `image_imshow` | PASS | `True` | - | - | 52 |
| `clean_25_negative_values_unicode_minus` | clean | `bars_horizontal` | PASS | `True` | - | - | 44 |
| `defect_01_claim_mismatch_bars` | defective | `bars_grouped` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 42 |
| `defect_02_claim_mismatch_lines` | defective | `lines_dates` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 56 |
| `defect_03_claim_mismatch_quadmesh` | defective | `quadmesh` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 40 |
| `defect_04_claim_mismatch_boxplot` | defective | `boxplot` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 37 |
| `defect_05_claim_mismatch_hist` | defective | `histogram` | PASS | `False` | claim_number_mismatch | claim_number_mismatch | 41 |
| `defect_06_truncated_vbar` | defective | `bars_grouped` | PASS | `False` | bar_baseline_nonzero | bar_baseline_nonzero | 37 |
| `defect_07_truncated_hbar` | defective | `bars_horizontal` | PASS | `False` | bar_baseline_nonzero | bar_baseline_nonzero | 29 |
| `defect_08_truncated_grouped_bars` | defective | `bars_grouped` | PASS | `False` | bar_baseline_nonzero | bar_baseline_nonzero | 37 |
| `defect_09_tiny_text_wide_chat` | defective | `bars_grouped` | PASS | `False` | text_too_small | text_too_small | 42 |
| `defect_10_tiny_text_explicit_small_font` | defective | `lines_dates` | PASS | `False` | text_too_small | text_too_small | 45 |
| `defect_11_tiny_text_narrow_450` | defective | `lines_dates` | PASS | `False` | text_too_small | text_too_small | 40 |
| `defect_12_tiny_text_multipanel_chat` | defective | `multi_panel` | PASS | `False` | text_too_small | text_too_small | 125 |
| `defect_13_overlapping_annotations` | defective | `scatter_ols` | PASS | `False` | text_overlaps | text_overlaps | 46 |
| `defect_14_overlapping_xticks` | defective | `bars_grouped` | PASS | `False` | text_overlaps | text_overlaps | 54 |
| `defect_15_overlapping_line_end_labels` | defective | `lines_dates` | PASS | `False` | text_overlaps | text_overlaps | 44 |
| `defect_16_struck_by_data_line` | defective | `lines_dates` | PASS | `False` | text_struck_by_line | text_struck_by_line | 46 |
| `defect_17_struck_by_reference_line` | defective | `lines_dates` | PASS | `False` | text_struck_by_line | text_struck_by_line | 45 |
| `defect_18_struck_frameless_legend` | defective | `framed_legend` | PASS | `False` | text_struck_by_line | text_struck_by_line | 43 |
| `defect_19_rainbow_imshow_jet` | defective | `image_imshow` | PASS | `False` | rainbow_colormap | rainbow_colormap | 47 |
| `defect_20_rainbow_quadmesh_hsv` | defective | `quadmesh` | PASS | `False` | rainbow_colormap | rainbow_colormap | 41 |
| `defect_21_rainbow_scatter_rainbow` | defective | `scatter_ols` | PASS | `False` | rainbow_colormap | rainbow_colormap | 54 |
| `defect_22_malformed_doubled_pct` | defective | `bars_grouped` | PASS | `False` | text_malformed | text_malformed | 34 |
| `defect_23_malformed_nan_junk` | defective | `lines_dates` | PASS | `False` | text_malformed | text_malformed | 40 |
| `defect_24_malformed_ascii_minus` | defective | `bars_grouped` | PASS | `False` | text_malformed | text_malformed | 29 |
| `defect_25_clipped_right_edge` | defective | `lines_dates` | PASS | `False` | text_clipped | text_clipped | 24 |
