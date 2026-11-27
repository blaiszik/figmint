# figure-bench results: v01_100_sonnet55_matplotlib_plain (matplotlib-plain arm)

- Passed: **35 / 100** (31 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 64 / 100
- Reply delivers the figure (<= 60 words of prose): 100 / 100 replies (0 not provided)
- Time to pass: median 10.3 s, mean 10.9 s, p90 14.9 s, total 381.4 s (first submit median 10.54 s, render median 0.457 s)
- Core tasks: {'tasks': 75, 'passed': 25, 'passed_first_try': 21, 'answers_correct': 47, 'replies_deliver': 75, 'median_seconds_to_pass': 10.3, 'median_seconds_total': 10.7, 'mean_seconds_to_pass': 10.9, 'p90_seconds_to_pass': 14.9}
- Held-out tasks: {'tasks': 25, 'passed': 10, 'passed_first_try': 10, 'answers_correct': 17, 'replies_deliver': 25, 'median_seconds_to_pass': 10.4, 'median_seconds_total': 11.5, 'mean_seconds_to_pass': 10.9, 'p90_seconds_to_pass': 13.7}
- Neutral audit, first submission: {'saved': '92/100', 'clean': '31/100', 'text_legible': '44/92', 'no_text_overlap': '86/92', 'no_text_struck_by_lines': '73/92', 'text_well_formed': '76/92', 'no_text_clipped': '87/92', 'headline_has_number': '79/92', 'headline_correct': '62/92', 'reply_correct': '63/100', 'uncertainty_named': '38/51', 'median_min_text_px': 10.9, 'with_legend': 41}
- Neutral audit, final submission: {'saved': '99/100', 'clean': '35/100', 'text_legible': '49/99', 'no_text_overlap': '93/99', 'no_text_struck_by_lines': '80/99', 'text_well_formed': '81/99', 'no_text_clipped': '94/99', 'headline_has_number': '84/99', 'headline_correct': '64/99', 'reply_correct': '63/100', 'uncertainty_named': '43/56', 'median_min_text_px': 10.9, 'with_legend': 44}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Total (s) | Render (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | ---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | no | 1 | 0 | — | 16.8 | 0.403 | yes | pass | text_well_formed, no_text_clipped | Reranker adds ~1.6 pts; encoder gain is within noise |
| 02_ab_latency | no | 1 | 0 | — | 9.4 | 0.672 | yes | pass | text_legible, text_well_formed | New flow median -83 ms vs control (95% CI -112 to -53) |
| 03_dose_response | no | 1 | 0 | — | 14.7 | 2.903 | no | pass | text_legible | Dose–response by compound (dots = replicates, lines = Hill fit) |
| 04_battery_fade | no | 1 | 0 | — | 11.1 | 0.468 | no | pass | text_legible | VC-3 excluded (crimping defect, fails after cycle 200). Thin lines = individual cells; thick = mean. 1C/1C, 25 °C. |
| 05_retrofit | no | 1 | 0 | — | 15.4 | 0.526 | yes | pass | text_well_formed, no_text_clipped | The retrofit cut energy use
by ~18–28%; the Gym barely moved |
| 06_energy_mix | no | 1 | 0 | — | 16.0 | 0.436 | yes | pass | text_legible, no_text_clipped | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | no | 1 | 0 | — | 11.0 | 0.499 | no | pass | text_legible, text_well_formed | p53 targets are switched on by the drug; housekeeping stays flat |
| 08_hall_petch | yes | 2 | 0 | 15.3 | 15.3 | 0.866 | no | pass | — | Hall–Petch fits by alloy |
| 09_eval_matrix | no | 1 | 0 | — | 10.3 | 0.555 | yes | pass | text_legible | Weakest cell: Swahili math (45%, boxed) |
| 10_incident | no | 1 | 0 | — | 12.2 | 0.577 | no | pass | text_legible, no_text_struck_by_lines | Only payments spiked; other services stayed near their normal rates |
| 11_forest_meta | no | 1 | 0 | — | 9.3 | 0.518 | yes | pass | text_legible | Extended prophylaxis cuts thromboembolism odds: pooled OR 0.75 (0.67–0.84)
Orange: COAST-3 and PLAINS-5 CIs cross 1.0 |
| 12_survival_km | yes | 3 | 0 | 20.2 | 20.2 | 1.183 | no | pass | — | Combination delays progression: median PFS +6 months (95% CI bands) |
| 13_trap_overlapping_ci | yes | 3 | 0 | 13.7 | 13.7 | 1.201 | no | pass | — | Candidate F1 vs baseline: 95% CIs overlap, no clear winner (n=5 seeds) |
| 14_trap_outlier_sensor | no | 1 | 0 | — | 9.8 | 0.486 | yes | pass | text_legible, no_text_struck_by_lines | Yield rises then plateaus near 84% above ~230 °C |
| 15_edit_switch_baseline | yes | 1 | 0 | 8.5 | 8.5 | 0.423 | yes | pass | — | cache_b is 31% faster than control_v2 (production) |
| 16_calibration_reliability | yes | 1 | 0 | 10.1 | 10.1 | 0.423 | no | pass | — | Temperature scaling cuts ECE by 86% (0.118 → 0.017) |
| 17_gpu_roofline_kernels | no | 1 | 0 | — | 9.2 | 0.549 | yes | pass | text_legible, no_text_overlap, no_text_struck_by_lines | H100 Roofline: moe_grouped_gemm reaches only 49% of the compute roof |
| 18_db_query_plan_tail | no | 1 | 0 | — | 10.2 | 0.457 | yes | pass | text_legible | Composite index on orders(customer_id, created_at), 500 queries per endpoint |
| 19_trap_dual_axis_spurious | no | 1 | 0 | — | 8.7 | 0.475 | yes | pass | text_legible | Raw levels: r = 0.99 (shared upward trend) |
| 20_trap_survivorship_bias | no | 1 | 0 | — | 7.8 | 0.423 | no | pass | text_legible | Q3 satisfaction: active-only view would overstate happiness |
| 21_edit_normalize_per_capita | no | 2 | 0 | — | 14.1 | 0.764 | no | pass | text_legible | Small counties carry the highest hospital admission risk |
| 22_edit_split_confounder | no | 1 | 0 | — | 12.9 | 0.493 | yes | pass | no_text_overlap, no_text_struck_by_lines | BF16 keeps improving; FP8 turns upward after ~40k |
| 23_surface_narrow_oncall | no | 1 | 0 | — | 7.5 | 0.435 | no | pass | no_text_struck_by_lines, no_text_clipped | checkout-api is nearly out of budget |
| 24_surface_html_interactive_report | no | 1 | 0 | — | 11.2 | 0.407 | yes | pass | text_well_formed | Android F1 fell 9.4 pts since May; other slices are within noise |
| 25_repair_truncated_and_rainbow | no | 1 | 0 | — | 8.8 | 0.437 | yes | pass | text_legible | Error bars: ±1 SD across 5 seeds. Y-axis starts at 0. |
| h06_enzyme_michaelis | no | 1 | 0 | — | 14.0 | 2.961 | no | pass | text_legible, no_text_struck_by_lines | E142A shifts Km, leaves Vmax intact |
| h07_cohort_attrition | no | 1 | 0 | — | 8.2 | 0.492 | yes | pass | text_legible | 540 of 2,400 patients (22.5%) completed the 12-week endpoint
Largest drop (red): age/diagnosis eligibility, −720 |
| h08_trap_overlap_clinical | no | 2 | 0 | — | 11.9 | 0.781 | no | pass | text_well_formed | Arms overlap heavily; difference not distinct (Welch p=0.58) |
| h09_trap_bad_batch | no | 1 | 0 | — | 12.7 | 0.501 | yes | pass | text_legible | Treated raises OD ~1.6x over control (0.67 vs 0.41) once failed plate P4 is excluded |
| h10_edit_highlight_subset | no | 1 | 0 | — | 8.8 | 0.45 | no | pass | text_legible | Error bars: ±1 SD, n=6 coupons per coating. |
| h11_chrome_trace_build | no | 1 | 0 | — | 10.2 | 0.322 | yes | pass | text_legible | lto_link, a serial stage, takes 52 s (44%) of the 118 s build |
| h12_hyperfine_within_noise | yes | 1 | 0 | 8.1 | 8.1 | 0.339 | no | pass | — | Difference in means is well within run-to-run noise (25 runs each) |
| h13_narrow_ide_sidebar | yes | 1 | 0 | 7.7 | 7.7 | 0.402 | yes | pass | — | Test-suite duration, 80 runs each |
| h14_repair_boxplot_claim | no | 1 | 0 | — | 11.0 | 0.423 | yes | pass | no_text_struck_by_lines | ap-northeast median is 141 ms, 3.0× us-east (48 ms) |
| h15_repair_multipanel_ci | no | 1 | 0 | — | 13.3 | 0.475 | yes | pass | text_legible, no_text_struck_by_lines | Cosine warmup overtakes baseline at epoch 6, ending +5.4 pts accuracy |
| h16_pharmacokinetics_auc | no | 3 | 0 | — | 22.4 | 1.03 | — | pass | script_runs, one_figure_saved |  |
| h17_catalyst_selectivity_tradeoff | yes | 1 | 0 | 7.9 | 7.9 | 0.43 | yes | pass | — | Highest single-pass yield: In2O3-ZrO2 (68.0 ± 1.8%) |
| h18_gc_pause_tail_cdf | yes | 1 | 0 | 9.9 | 9.9 | 0.548 | yes | pass | — | GC pause tail: G1GC reaches 142 ms at p99.9 |
| h19_distributed_scaling_eff | yes | 1 | 0 | 8.8 | 8.8 | 0.458 | no | pass | — |  |
| h1_survey | no | 1 | 0 | — | 13.0 | 0.407 | yes | pass | text_legible, no_text_overlap | Support is lowest at 42% satisfied |
| h20_trap_ecological_fallacy | no | 1 | 0 | — | 9.6 | 0.462 | no | pass | text_legible, text_well_formed | Districts with more tutoring score higher, but within each district
more tutoring goes with lower scores (diamonds = district means) |
| h21_trap_missing_zero_truncation | yes | 1 | 0 | 12.6 | 12.6 | 0.425 | yes | pass | — | Dots = individual units (n=6); red line = mean. Y-axis starts at 93%, not zero. |
| h22_edit_add_control_and_exclude_drift | yes | 1 | 0 | 16.4 | 16.4 | 0.455 | yes | pass | — | R07 excluded: qc_status = temp_drift_fault (41.5 a.u.). Welch CI for lift. |
| h23_surface_terminal_ci_diff | no | 1 | 0 | — | 11.5 | 0.437 | yes | pass | text_legible | Decompression, mean ± SD (n=8) |
| h24_surface_narrow_pr_comment | yes | 1 | 0 | 13.4 | 13.4 | 0.47 | yes | pass | — | type_check saves most: 683 → 409 MB (−40%) |
| h25_repair_ci_and_wrong_p | no | 1 | 0 | — | 15.7 | 0.396 | yes | pass | text_well_formed | Difference +2.3 (+3.5%), 95% CI [-3.3, 8.0]; /t/=0.88 < 2.14, not significant |
| h2_spectra | yes | 1 | 0 | 11.0 | 11.0 | 0.408 | yes | pass | — | 400 °C anneal red-shifts the peak by ~25 nm; 200 °C by ~5 nm (one step) |
| h3_wait_times | no | 1 | 0 | — | 13.5 | 0.699 | no | pass | text_legible | South is slower only for less urgent patients (levels 3–5); levels 1–2 are the same |
| h4_scaling | yes | 1 | 0 | 12.9 | 12.9 | 0.476 | yes | pass | — | Mixture-of-experts scales fastest (exponent −0.063) |
| h5_budget | no | 1 | 0 | — | 10.6 | 0.412 | yes | pass | text_well_formed | Libraries took the deepest cut (−18%); Housing grew most (+14%) |
| pt01_volcano_omics | no | 1 | 0 | — | 11.2 | 0.457 | no | pass | text_legible | 3 of 120 genes pass /log2FC/ ≥ 1.5 and adj. p < 0.01 |
| pt02_raman_peaks | no | 1 | 0 | — | 12.5 | 0.431 | yes | pass | text_legible, no_text_struck_by_lines | G band shifts +16 cm⁻¹ at 600 °C, +8 cm⁻¹ at 350 °C; D band weakens |
| pt03_arrhenius_kinetics | yes | 1 | 0 | 15.2 | 15.2 | 0.554 | no | pass | — | Arrhenius plot: Cat-Pt vs Cat-Ni, 500–625 K |
| pt04_rl_seed_curves | no | 1 | 0 | — | 12.7 | 0.433 | yes | pass | text_legible, no_text_clipped | Mean ± 1 SD across 6 seeds |
| pt05_alloy_replicates | no | 1 | 0 | — | 12.0 | 0.401 | no | pass | text_legible | Only T6 clears 420 MPa on every coupon; T6-aged has 2 failures |
| pt06_ocean_ph_trend | no | 1 | 0 | — | 7.9 | 0.46 | yes | pass | text_legible, text_well_formed | Southern Ocean is acidifying fastest: -0.026 pH/decade (-0.051 over 20 yr) |
| pt07_trap_no_speedup | yes | 1 | 0 | 12.3 | 12.3 | 0.443 | yes | pass | — | solver_v2 is 2.8 ms faster on average, within noise
(Welch t≈0.5; 10 trials each; bars = mean ± 95% CI) |
| pt08_trap_simpson | no | 1 | 0 | — | 12.4 | 0.44 | no | pass | text_legible | Treatment looks worse overall only because it is given mostly to severe patients;
it does better in both severity groups |
| pt09_trap_small_n | yes | 1 | 0 | 9.6 | 9.6 | 0.431 | yes | pass | — | Mean +27%, but replicates overlap (n=3 each) |
| pt10_trap_near_zero_pct | no | 1 | 0 | — | 9.7 | 0.414 | yes | pass | text_legible | Line-C rose from 0.02% to 0.14%; other lines unchanged |
| pt11_trap_truncated_bait | yes | 1 | 0 | 10.6 | 10.6 | 0.505 | yes | pass | — | v4.2 raised success rate in every region (overall 97.4% → 98.6%) |
| pt12_trap_missing_control | yes | 1 | 0 | 7.3 | 7.3 | 0.433 | no | pass | — | Symptom score change vs placebo (lower = better) |
| pt13_edit_log_scale | no | 1 | 0 | — | 9.9 | 0.621 | yes | pass | text_legible, no_text_struck_by_lines | CMP-C is 181 ng/mL at 24 h, above the 50 ng/mL floor |
| pt14_edit_add_uncertainty | yes | 3 | 0 | 14.5 | 14.5 | 1.136 | yes | pass | — | High dose raises secretion 63% over control (+123 pg/mL) |
| pt15_edit_fix_units | no | 1 | 0 | — | 11.4 | 0.419 | yes | pass | text_legible | Board-D cuts peak load power to 1.49 W (−52% vs Board-A) |
| pt16_hyperfine_diff | yes | 1 | 0 | 8.7 | 8.7 | 0.294 | no | pass | — | JSON parser sped up; YAML unchanged |
| pt17_pytest_regression | no | 1 | 0 | — | 10.9 | 0.323 | no | pass | text_legible, text_well_formed | One endpoint regressed; the rest are within noise |
| pt18_ci_pipeline_timeline | no | 1 | 0 | — | 12.4 | 0.497 | yes | pass | text_legible | integration-shard-3 (585 s) holds package-artifacts back until 735 s
Critical path in red; hatched = idle waiting on shard-3 |
| pt19_k6_latency_deploy | no | 1 | 0 | — | 12.8 | 0.448 | yes | pass | text_legible | After deploy, p99 jumps to ~750 ms (SLA 500 ms) while p50 stays ~43 ms |
| pt20_bundle_waterfall | no | 1 | 0 | — | 12.1 | 0.305 | yes | pass | text_legible, no_text_overlap, text_well_formed | dist/app.bundle.js grew 240 KB (+50%); date-locale-pack accounts for 89% |
| pt21_llm_pareto_frontier | no | 1 | 0 | — | 11.2 | 0.516 | yes | pass | text_legible, no_text_struck_by_lines | Only 3 of 10 configs are Pareto-optimal on accuracy, cost, and latency |
| pt22_signup_funnel | no | 1 | 0 | — | 7.1 | 0.43 | yes | pass | text_legible, text_well_formed | Email verification loses 46% of users, the biggest drop in the funnel |
| pt23_memory_soak_leak | no | 1 | 0 | — | 13.4 | 0.453 | yes | pass | text_legible, no_text_overlap, no_text_struck_by_lines | worker-ingest leaks ~18 MB/h; others are flat |
| pt24_narrow_phone_alert | no | 1 | 0 | — | 13.7 | 0.421 | no | pass | no_text_struck_by_lines | Only eu-west spiked; rollback fixed it |
| pt25_slide_quarterly_perf | no | 1 | 0 | — | 10.4 | 0.473 | yes | pass | no_text_struck_by_lines | Asia-Pacific latency fell 35% and throughput rose 39% after edge caching |
| pt26_dark_dashboard_card | yes | 1 | 0 | 10.8 | 10.8 | 0.426 | yes | pass | — | Hit rate % (dots = 8 traces, orange = mean) |
| pt27_terminal_only_bench | yes | 1 | 0 | 9.0 | 9.0 | 0.401 | no | pass | — |  |
| pt28_repair_ablation_bars | yes | 1 | 0 | 10.7 | 10.7 | 0.428 | yes | pass | — | Removing query rewrite costs 5.5 F1 points |
| pt29_repair_jet_heatmap | yes | 1 | 0 | 8.6 | 8.6 | 0.458 | yes | pass | — | Accuracy is 73.2%, not 96.4%; search → infra is the main misroute
(46 of 201 search tickets, 23%) |
| pt30_repair_line_struck | yes | 1 | 0 | 12.0 | 12.0 | 0.428 | yes | pass | — | v2.0 peaks at 4,820 req/s (+48% over v1.0) |
| pt31_bland_altman | no | 1 | 0 | — | 12.8 | 0.434 | no | pass | text_legible, text_well_formed | Bland–Altman: wearable vs arterial SaO2 (n=60) |
| pt32_xrd_phase_shift | no | 1 | 0 | — | 13.9 | 0.47 | yes | pass | text_legible | Mean scan ± SD (n=3) |
| pt33_crispr_screen_rank | no | 1 | 0 | — | 8.1 | 0.449 | no | pass | text_legible, no_text_struck_by_lines, text_well_formed | CRISPR synthetic-lethality screen, 50 genes |
| pt34_climate_ensemble_fan | yes | 1 | 0 | 10.3 | 10.3 | 0.459 | yes | pass | — | 2100 median warming gap: 2.60 °C (SSP3-7.0 vs SSP1-2.6) |
| pt35_cache_eviction_hitrate | no | 1 | 0 | — | 11.0 | 0.442 | no | pass | text_legible, no_text_struck_by_lines | Miss-ratio curves (mean, band = min–max of 5 replays) |
| pt36_token_throughput_batch | no | 1 | 0 | — | 9.6 | 0.431 | yes | pass | no_text_struck_by_lines | Throughput vs TTFT: batch 16 is the best within the SLA |
| pt37_flaky_ci_heatmap | yes | 1 | 0 | 10.8 | 10.8 | 0.487 | no | pass | — | Weekly CI flake rate by test module (%) |
| pt38_cloud_cost_waterfall | no | 3 | 0 | — | 15.1 | 1.3 | yes | pass | text_legible, text_well_formed | Cloud bill rose \$41.2k (+32%), Sep to Oct; GPU inference drove +\$34.8k |
| pt39_trap_multiple_testing | yes | 1 | 0 | 8.9 | 8.9 | 0.474 | yes | pass | — | 20 metrics: none significant after FDR correction (min BH-adj p=0.76) |
| pt40_trap_heavy_tail_mean | yes | 1 | 0 | 12.3 | 12.3 | 0.515 | yes | pass | — | New pricing's +47% mean comes from 3 orders over $1,800;
median order is slightly lower |
| pt41_trap_denominator_shift | no | 1 | 0 | — | 7.2 | 0.421 | yes | pass | no_text_overlap, no_text_struck_by_lines | Alert rate fell 15% (13.0 → 11.0) despite more raw alerts |
| pt42_trap_cherry_picked_window | no | 1 | 0 | — | 9.2 | 0.485 | yes | pass | text_legible | Signups are flat at ~100k/week; W09–W12 rise is a rebound from a W09 dip |
| pt43_edit_sort_and_annotate_target | no | 1 | 0 | — | 8.7 | 0.494 | yes | pass | text_legible, text_well_formed | Dallas and Newark miss the 95% SLA |
| pt44_edit_replace_pie_with_delta | no | 1 | 0 | — | 9.0 | 0.492 | yes | pass | text_legible, text_well_formed | Organic Search lost 9.4 pp of traffic share; Paid Search gained 5.6 pp |
| pt45_edit_switch_to_cdf_tails | no | 1 | 0 | — | 7.6 | 0.469 | no | pass | text_legible | checkout_v3 has a slow tail that the mean hides |
| pt46_surface_slide_exec_kpi | yes | 1 | 0 | 9.1 | 9.1 | 0.446 | yes | pass | — | Gross margin up 11.4 pp in 5 quarters, to 68.2% |
| pt47_surface_dark_noc_monitor | yes | 1 | 0 | 9.3 | 9.3 | 0.439 | no | pass | — | Edge PoP TTFB, 12 probes each (bar = median) |
| pt48_repair_dual_axis_spaghetti | no | 1 | 0 | — | 9.1 | 0.488 | no | pass | no_text_struck_by_lines | Cluster metrics over 14 days: Day-10 incident |
| pt49_repair_pie_and_clipped_labels | yes | 1 | 0 | 7.4 | 7.4 | 0.416 | yes | pass | — | Timeouts are 31.4% of failures, not 42% (n = 1,000) |
| pt50_repair_unlabelled_log_scatter | yes | 1 | 0 | 7.5 | 7.5 | 0.517 | no | pass | — |  |
