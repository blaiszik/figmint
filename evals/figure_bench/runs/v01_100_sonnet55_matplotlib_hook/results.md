# figure-bench results: v01_100_sonnet55_matplotlib_hook (matplotlib-hook arm)

- Passed: **91 / 100** (57 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 73 / 100
- Reply delivers the figure (<= 60 words of prose): 100 / 100 replies (0 not provided)
- Time to pass: median 13.0 s, mean 14.1 s, p90 21.1 s, total 1285.3 s (first submit median 11.08 s, render median 0.611 s)
- Core tasks: {'tasks': 75, 'passed': 68, 'passed_first_try': 41, 'answers_correct': 53, 'replies_deliver': 75, 'median_seconds_to_pass': 13.0, 'median_seconds_total': 14.2, 'mean_seconds_to_pass': 14.1, 'p90_seconds_to_pass': 21.1}
- Held-out tasks: {'tasks': 25, 'passed': 23, 'passed_first_try': 16, 'answers_correct': 20, 'replies_deliver': 25, 'median_seconds_to_pass': 13.0, 'median_seconds_total': 13.6, 'mean_seconds_to_pass': 14.1, 'p90_seconds_to_pass': 18.5}
- Neutral audit, first submission: {'saved': '97/100', 'clean': '57/100', 'text_legible': '94/97', 'no_text_overlap': '86/97', 'no_text_struck_by_lines': '77/97', 'text_well_formed': '82/97', 'no_text_clipped': '91/97', 'headline_has_number': '81/97', 'headline_correct': '58/97', 'reply_correct': '84/100', 'uncertainty_named': '36/55', 'median_min_text_px': 15.3, 'with_legend': 36}
- Neutral audit, final submission: {'saved': '100/100', 'clean': '91/100', 'text_legible': '100/100', 'no_text_overlap': '99/100', 'no_text_struck_by_lines': '95/100', 'text_well_formed': '99/100', 'no_text_clipped': '98/100', 'headline_has_number': '95/100', 'headline_correct': '73/100', 'reply_correct': '84/100', 'uncertainty_named': '39/57', 'median_min_text_px': 15.3, 'with_legend': 37}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Total (s) | Render (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | ---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | no | 3 | 0 | — | 22.2 | 1.506 | yes | pass | text_well_formed | Reranker: +1.6 pts, beyond noise
Small encoder: -0.5, within noise |
| 02_ab_latency | yes | 3 | 0 | 21.7 | 21.7 | 1.565 | yes | pass | — | New flow cuts median checkout latency 83 ms (424 to 341) |
| 03_dose_response | yes | 1 | 0 | 11.6 | 11.6 | 0.683 | no | pass | — | CPD-7 is most potent; CPD-4 is inactive |
| 04_battery_fade | yes | 1 | 0 | 12.6 | 12.6 | 0.46 | no | pass | — |  |
| 05_retrofit | yes | 3 | 0 | 20.0 | 20.0 | 1.42 | yes | pass | — | Retrofit cut use 28% (Lab annex), 18% (Library); Gym 3% |
| 06_energy_mix | yes | 3 | 0 | 21.6 | 21.6 | 1.729 | yes | pass | — | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | yes | 2 | 0 | 17.4 | 17.4 | 1.128 | no | pass | — | p53 targets up, proliferation down, housekeeping flat |
| 08_hall_petch | yes | 1 | 0 | 12.2 | 12.2 | 0.544 | no | pass | — |  |
| 09_eval_matrix | yes | 1 | 0 | 11.3 | 11.3 | 0.557 | yes | pass | — | Swahili math (45.4%) is the one bad cell;
Swahili is lowest in every task |
| 10_incident | yes | 2 | 0 | 15.4 | 15.4 | 1.28 | yes | pass | — | Only payments spiked: 278× its median on Nov 13 |
| 11_forest_meta | no | 3 | 0 | — | 15.1 | 1.468 | yes | pass | no_text_clipped | Pooled OR 0.75 (0.67–0.84) clears 1.0; COAST-3 and PLAINS-5 cross 1.0 |
| 12_survival_km | yes | 1 | 0 | 14.1 | 14.1 | 0.616 | no | pass | — | Combination shifts median PFS by 6 months (95% CI bands) |
| 13_trap_overlapping_ci | yes | 1 | 0 | 12.5 | 12.5 | 0.474 | no | pass | — | cand_b is not clearly better than baseline
Mean ± 95% CI overlaps; dots are the 5 seeds |
| 14_trap_outlier_sensor | yes | 3 | 0 | 16.0 | 16.0 | 1.561 | yes | pass | — | Yield rises from 65% to 84.7% with temperature, then flattens |
| 15_edit_switch_baseline | yes | 1 | 0 | 9.4 | 9.4 | 0.471 | yes | pass | — | cache_b handles 31% more requests/s than control_v2 (812 vs 620) |
| 16_calibration_reliability | yes | 1 | 0 | 9.7 | 9.7 | 0.515 | no | pass | — | Temperature scaling cuts ECE by 86% (AUROC 0.91 both) |
| 17_gpu_roofline_kernels | no | 3 | 0 | — | 28.1 | 1.893 | yes | pass | no_text_struck_by_lines | moe_grouped_gemm reaches only 49% of the roof |
| 18_db_query_plan_tail | yes | 1 | 0 | 10.1 | 10.1 | 0.519 | no | pass | — | orders_join: tail fixed |
| 19_trap_dual_axis_spurious | yes | 3 | 0 | 20.1 | 20.1 | 1.433 | yes | pass | — | Raw r = 0.99 vanishes (r = −0.07) once the shared trend is removed |
| 20_trap_survivorship_bias | yes | 1 | 0 | 11.4 | 11.4 | 0.512 | yes | pass | — | Q3 satisfaction: all 60 accounts, mean 64.6 |
| 21_edit_normalize_per_capita | yes | 1 | 0 | 7.9 | 7.9 | 0.469 | yes | pass | — | Cedar-Flats has the highest admission rate (155 per 100k) |
| 22_edit_split_confounder | yes | 3 | 0 | 21.2 | 21.2 | 1.538 | no | pass | — | FP8 loss diverges from BF16 after ~45k steps |
| 23_surface_narrow_oncall | yes | 2 | 0 | 11.2 | 11.2 | 0.966 | yes | pass | — | checkout-api has 21.4% budget left |
| 24_surface_html_interactive_report | yes | 1 | 0 | 9.4 | 9.4 | 0.49 | yes | pass | — | Android F1 fell 9.4 points since May (86.8 to 77.4) |
| 25_repair_truncated_and_rainbow | yes | 1 | 0 | 9.0 | 9.0 | 0.462 | yes | pass | — | Error bars: ±1 SD across 5 seeds |
| h06_enzyme_michaelis | yes | 1 | 0 | 14.4 | 14.4 | 0.723 | yes | pass | — | E142A raises Km ~3.7x; Vmax is similar |
| h07_cohort_attrition | yes | 3 | 0 | 18.2 | 18.2 | 1.461 | yes | pass | — | 540 of 2,400 screened patients complete the 12-week endpoint |
| h08_trap_overlap_clinical | yes | 3 | 0 | 17.7 | 17.7 | 1.394 | yes | pass | — | Dots = patients (n=18/arm); black = mean ± 95% CI |
| h09_trap_bad_batch | yes | 1 | 0 | 11.9 | 11.9 | 0.508 | no | pass | — | Treated is ~1.6x control on every valid plate
(P4 excluded: washer malfunction) |
| h10_edit_highlight_subset | yes | 1 | 0 | 11.8 | 11.8 | 0.465 | no | pass | — | TiN-3 and BN-6 fail the 5.0% limit after 1,000 cycles |
| h11_chrome_trace_build | no | 3 | 0 | — | 21.9 | 1.088 | yes | pass | no_text_overlap | lto_link is 43.8% of build time, on one thread |
| h12_hyperfine_within_noise | yes | 1 | 0 | 15.4 | 15.4 | 0.342 | yes | pass | — | Mean differs by 7 ms, well inside ±1 s.d. (~19 ms): noise |
| h13_narrow_ide_sidebar | yes | 1 | 0 | 13.6 | 13.6 | 0.445 | yes | pass | — | Run duration, 80 runs per mode |
| h14_repair_boxplot_claim | yes | 1 | 0 | 8.4 | 8.4 | 0.479 | yes | pass | — | ap-northeast median is 141 ms, 3.0x us-east (48 ms) |
| h15_repair_multipanel_ci | yes | 1 | 0 | 9.9 | 9.9 | 0.503 | yes | pass | — | Cosine warmup overtakes baseline at epoch 6 and ends 5.36 pts more accurate |
| h16_pharmacokinetics_auc | yes | 1 | 0 | 13.0 | 13.0 | 0.562 | yes | pass | — | Mean ± SD, n = 8 per group |
| h17_catalyst_selectivity_tradeoff | yes | 1 | 0 | 9.8 | 9.8 | 0.501 | yes | pass | — | In2O3-ZrO2 gives the highest yield (68.0%) |
| h18_gc_pause_tail_cdf | yes | 1 | 0 | 10.4 | 10.4 | 0.511 | no | pass | — | G1GC pauses diverge in the tail |
| h19_distributed_scaling_eff | yes | 3 | 0 | 23.8 | 23.8 | 1.532 | yes | pass | — | At 64 nodes NCCL keeps 81% efficiency vs 22% for Gloo-TCP |
| h1_survey | yes | 1 | 0 | 12.0 | 12.0 | 0.444 | yes | pass | — | Support is lowest at 42% satisfied |
| h20_trap_ecological_fallacy | yes | 2 | 0 | 18.6 | 18.6 | 1.051 | yes | pass | — | Within every district, each tutoring hour goes with about 3 fewer points |
| h21_trap_missing_zero_truncation | yes | 1 | 0 | 11.8 | 11.8 | 0.461 | no | pass | — | Charger-D is most efficient (6 units each; line = mean) |
| h22_edit_add_control_and_exclude_drift | yes | 3 | 0 | 23.6 | 23.6 | 1.295 | yes | pass | — | R07 excluded (QC: temp_drift_fault, 41.5 a.u.).
Dots = valid runs; diamonds = mean ± 95% CI.
Lift 95% CI 4.9–7.1. |
| h23_surface_terminal_ci_diff | yes | 1 | 0 | 11.4 | 11.4 | 0.455 | yes | pass | — | lz4-fast: 2x faster; zstd-3: 59% better ratio |
| h24_surface_narrow_pr_comment | no | 3 | 0 | — | 24.1 | 1.499 | yes | pass | no_text_struck_by_lines | type_check: 683→409 MB, −40% |
| h25_repair_ci_and_wrong_p | yes | 1 | 0 | 13.8 | 13.8 | 0.542 | yes | pass | — | Difference +2.3 points (+3.5%), CIs overlap, p≈0.39 |
| h2_spectra | yes | 1 | 0 | 9.4 | 9.4 | 0.472 | yes | pass | — | 400 °C anneal shifts the peak 25 nm; 200 °C ~5 nm |
| h3_wait_times | yes | 1 | 0 | 10.9 | 10.9 | 0.485 | no | pass | — | South is slower only at triage levels 3–5; levels 1–2 match |
| h4_scaling | yes | 2 | 0 | 17.8 | 17.8 | 1.048 | yes | pass | — | Mixture-of-experts scales fastest (slope −0.063) |
| h5_budget | yes | 3 | 0 | 15.9 | 15.9 | 1.586 | yes | pass | — | Libraries: biggest cut (−18%); Housing: biggest rise (+14%) |
| pt01_volcano_omics | yes | 3 | 0 | 24.8 | 24.8 | 1.493 | no | pass | — | Only 3 of 120 genes pass both cutoffs; CXCL10 moves most |
| pt02_raman_peaks | yes | 1 | 0 | 11.3 | 11.3 | 0.494 | yes | pass | — | G band shifts +16 cm⁻¹ at 600 C, +8 at 350 C |
| pt03_arrhenius_kinetics | yes | 1 | 0 | 15.9 | 15.9 | 0.616 | no | pass | — | Pt stays faster at all T; Ni gap narrows 13× → 3× |
| pt04_rl_seed_curves | yes | 1 | 0 | 13.2 | 13.2 | 0.567 | yes | pass | — | SAC-tuned leads: 838 vs 749 (TD3), 704 (PPO) |
| pt05_alloy_replicates | yes | 1 | 0 | 11.0 | 11.0 | 0.498 | no | pass | — | T6-aged: 2 of 8 coupons fall below 420 MPa; T6 clears all 8 |
| pt06_ocean_ph_trend | yes | 3 | 0 | 16.8 | 16.8 | 1.636 | yes | pass | — | Southern Ocean loses 0.026 pH per decade, fastest of three |
| pt07_trap_no_speedup | yes | 1 | 0 | 14.2 | 14.2 | 0.495 | yes | pass | — | Dots: trials. Black: mean ± 95% CI. |
| pt08_trap_simpson | yes | 3 | 0 | 18.8 | 18.8 | 1.604 | yes | pass | — | Treatment beats control in both strata (95 vs 90%, 52 vs 40%);
the overall 58 vs 80% gap is case mix |
| pt09_trap_small_n | yes | 1 | 0 | 9.4 | 9.4 | 0.509 | yes | pass | — | Inhibitor mean is 27% higher, but n = 3 per group and points overlap |
| pt10_trap_near_zero_pct | yes | 3 | 0 | 20.5 | 20.5 | 1.521 | yes | pass | — | Line-C rose from 0.02% to 0.14%; other lines flat |
| pt11_trap_truncated_bait | yes | 1 | 0 | 10.8 | 10.8 | 0.494 | no | pass | — | v4.2 raised success rate in every region |
| pt12_trap_missing_control | yes | 1 | 0 | 9.9 | 9.9 | 0.467 | no | pass | — | Treated and placebo improved by the same amount (~14-15%) |
| pt13_edit_log_scale | yes | 1 | 0 | 9.4 | 9.4 | 0.622 | yes | pass | — | CMP-C is still at 180.82 ng/mL at 24 h, above the 50 ng/mL floor |
| pt14_edit_add_uncertainty | yes | 3 | 0 | 14.6 | 14.6 | 1.138 | yes | pass | — | High dose mean is 1.63x control (n=7 per condition) |
| pt15_edit_fix_units | yes | 1 | 0 | 6.5 | 6.5 | 0.462 | yes | pass | — | Board-D draws 1.49 W under load, 1.63 W less than Board-A |
| pt16_hyperfine_diff | yes | 1 | 0 | 12.8 | 12.8 | 0.374 | no | pass | — | Branch speeds up JSON parser only
bars: mean ± s.d., dots: 20 runs |
| pt17_pytest_regression | yes | 3 | 0 | 22.5 | 22.5 | 1.075 | yes | pass | — | search_query mean latency +42%; other endpoints change ≤4% |
| pt18_ci_pipeline_timeline | yes | 1 | 0 | 14.7 | 14.7 | 0.508 | yes | pass | — | integration-shard-3 (585 s) blocks package-artifacts;
the other shards sit idle 325–355 s |
| pt19_k6_latency_deploy | yes | 1 | 0 | 13.4 | 13.4 | 0.519 | no | pass | — | p99 exceeds the SLA every minute after deploy |
| pt20_bundle_waterfall | yes | 3 | 0 | 26.2 | 26.2 | 1.056 | yes | pass | — | Bundle grew 240.4 KB; date-locale adds 214.2 KB |
| pt21_llm_pareto_frontier | yes | 1 | 0 | 10.4 | 10.4 | 0.606 | yes | pass | — | 3 of 10 configs are Pareto-optimal; 7 are strictly dominated |
| pt22_signup_funnel | yes | 3 | 0 | 16.3 | 16.3 | 1.438 | yes | pass | — | Email verification loses 46% of users |
| pt23_memory_soak_leak | yes | 3 | 0 | 23.4 | 23.4 | 1.534 | yes | pass | — | worker-ingest leaks 18 MB/h and reaches the 2 GB OOM cap at hour 90 |
| pt24_narrow_phone_alert | no | 3 | 0 | — | 25.0 | 1.457 | yes | pass | no_text_struck_by_lines | eu-west alone hit 14.3%; rollback fixed it |
| pt25_slide_quarterly_perf | yes | 1 | 0 | 10.7 | 10.7 | 0.526 | no | pass | — | p95 latency (ms, lower is better) |
| pt26_dark_dashboard_card | yes | 1 | 0 | 14.5 | 14.5 | 0.523 | no | pass | — | Hit rate |
| pt27_terminal_only_bench | yes | 1 | 0 | 9.3 | 9.3 | 0.426 | no | pass | — |  |
| pt28_repair_ablation_bars | yes | 1 | 0 | 11.7 | 11.7 | 0.438 | yes | pass | — | Query rewrite adds 5.5 points of F1 (0.763 → 0.818) |
| pt29_repair_jet_heatmap | yes | 1 | 0 | 8.5 | 8.5 | 0.503 | yes | pass | — | Accuracy is 73.2% (732/1,000); search tickets misrouted
to infra (46) is the top error |
| pt30_repair_line_struck | no | 3 | 0 | — | 19.7 | 1.488 | yes | pass | no_text_struck_by_lines | v2.0 peaks at 4,820 req/s (+48% over v1.0) |
| pt31_bland_altman | yes | 3 | 0 | 17.6 | 17.6 | 1.546 | yes | pass | — | Error is larger and more variable in the hypoxic range
(bias 2.24 vs 1.21 points) |
| pt32_xrd_phase_shift | yes | 3 | 0 | 20.5 | 20.5 | 1.653 | yes | pass | — | Δ2θ = 0.70 ± 0.01° |
| pt33_crispr_screen_rank | yes | 3 | 0 | 15.4 | 15.4 | 1.558 | yes | pass | — | 4 genes pass FDR < 0.05; PRMT5 is strongest at −3.45 |
| pt34_climate_ensemble_fan | yes | 1 | 0 | 9.9 | 9.9 | 0.471 | yes | pass | — | 2100 warming gap: 2.60 °C (SSP3-7.0 vs SSP1-2.6) |
| pt35_cache_eviction_hitrate | no | 3 | 0 | — | 20.1 | 1.558 | yes | pass | no_text_struck_by_lines | S3-FIFO misses 7.1 points less than LRU at 256 MB |
| pt36_token_throughput_batch | yes | 3 | 0 | 21.0 | 21.0 | 1.491 | yes | pass | — | Batch 16 gives 748 tok/s, the most within the 200 ms SLA |
| pt37_flaky_ci_heatmap | yes | 1 | 0 | 10.3 | 10.3 | 0.549 | no | pass | — | Flakiness is concentrated in auth_oauth, W04–W06 |
| pt38_cloud_cost_waterfall | yes | 3 | 0 | 19.5 | 19.5 | 1.506 | yes | pass | — | Cloud bill rose 41.2k USD; GPU inference added the most (+34.8) |
| pt39_trap_multiple_testing | yes | 3 | 0 | 21.1 | 21.1 | 1.619 | yes | pass | — | 0 of 20 metrics significant after correction |
| pt40_trap_heavy_tail_mean | yes | 1 | 0 | 11.6 | 11.6 | 0.663 | yes | pass | — | Mean +47% comes from 3 orders; median is flat |
| pt41_trap_denominator_shift | yes | 1 | 0 | 7.6 | 7.6 | 0.441 | yes | pass | — | Alert rate fell 15% (13.0 to 11.0) despite more raw alerts |
| pt42_trap_cherry_picked_window | no | 3 | 0 | — | 16.5 | 1.436 | yes | pass | no_text_clipped | Signups held near 100k/week for 16 weeks; W09–W12 is +18.4% off a dip |
| pt43_edit_sort_and_annotate_target | yes | 2 | 0 | 15.9 | 15.9 | 1.009 | yes | pass | — | Dallas and Newark miss the 95% SLA |
| pt44_edit_replace_pie_with_delta | yes | 3 | 0 | 14.5 | 14.5 | 1.427 | yes | pass | — | Organic Search lost 9.4 pp; Paid Search gained 5.6 pp |
| pt45_edit_switch_to_cdf_tails | yes | 1 | 0 | 14.6 | 14.6 | 0.451 | no | pass | — | checkout_v3 has a slow tail; means are equal (~146 ms) |
| pt46_surface_slide_exec_kpi | yes | 1 | 0 | 8.2 | 8.2 | 0.518 | yes | pass | — | Error bars: ±1 SD across 3 months per quarter |
| pt47_surface_dark_noc_monitor | yes | 1 | 0 | 12.2 | 12.2 | 0.477 | no | pass | — | TTFB per probe (12 per PoP); white bar = median |
| pt48_repair_dual_axis_spaghetti | yes | 3 | 0 | 17.2 | 17.2 | 1.642 | yes | pass | — | Day 10 peak: CPU 84%, errors 5.4% |
| pt49_repair_pie_and_clipped_labels | yes | 1 | 0 | 7.5 | 7.5 | 0.53 | yes | pass | — | Timeouts are 31.4% of failures, not 42% (n=1,000) |
| pt50_repair_unlabelled_log_scatter | yes | 1 | 0 | 9.9 | 9.9 | 0.693 | yes | pass | — | Parse time scales ~linearly: log-log slope 0.93, R² = 0.97 |
