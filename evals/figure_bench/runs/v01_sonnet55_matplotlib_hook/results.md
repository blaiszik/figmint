# figure-bench results: v01_sonnet55_matplotlib_hook (matplotlib-hook arm)

- Passed: **48 / 60** (15 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 39 / 60
- Reply delivers the figure (<= 60 words of prose): 60 / 60 replies (0 not provided)
- Time to pass: median 16.6 s, total 859.4 s
- Core tasks: {'tasks': 45, 'passed': 36, 'passed_first_try': 10, 'answers_correct': 31, 'replies_deliver': 45, 'median_seconds_to_pass': 17.7}
- Held-out tasks: {'tasks': 15, 'passed': 12, 'passed_first_try': 5, 'answers_correct': 8, 'replies_deliver': 15, 'median_seconds_to_pass': 16.4}
- Neutral audit, first submission: {'saved': '31/60', 'clean': '15/60', 'text_legible': '31/31', 'no_text_overlap': '25/31', 'no_text_struck_by_lines': '22/31', 'text_well_formed': '24/31', 'no_text_clipped': '30/31', 'headline_has_number': '21/31', 'headline_correct': '13/31', 'reply_correct': '48/60', 'uncertainty_named': '10/18', 'median_min_text_px': 15.3, 'with_legend': 13}
- Neutral audit, final submission: {'saved': '57/60', 'clean': '48/60', 'text_legible': '56/57', 'no_text_overlap': '55/57', 'no_text_struck_by_lines': '52/57', 'text_well_formed': '57/57', 'no_text_clipped': '55/57', 'headline_has_number': '50/57', 'headline_correct': '39/57', 'reply_correct': '47/60', 'uncertainty_named': '20/31', 'median_min_text_px': 15.3, 'with_legend': 22}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | yes | 2 | 0 | 23.8 | no | pass | — | Accuracy: dots = 5 seeds,
bar = mean ± 1 SD |
| 02_ab_latency | yes | 2 | 0 | 24.5 | yes | pass | — | New flow is faster: median 341 vs 424 ms, tail shorter |
| 03_dose_response | yes | 3 | 0 | 34.8 | yes | pass | — | CPD-7 is most potent (IC50 ≈ 12 nM); CPD-4 never reaches 50% |
| 04_battery_fade | yes | 1 | 0 | 16.3 | no | pass | — | Additives extend life ~1.3-1.5x over baseline |
| 05_retrofit | yes | 2 | 0 | 23.3 | yes | pass | — | Retrofit cut use 18–28%; the Gym barely moved |
| 06_energy_mix | no | 3 | 0 | — | yes | pass | text_legible | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | yes | 2 | 0 | 23.8 | yes | pass | — | p53 targets up ~2.2 log2; housekeeping flat |
| 08_hall_petch | yes | 3 | 0 | 24.0 | yes | pass | — | Cu-Zn Hall–Petch slope: 327 MPa·µm$^{1/2}$ |
| 09_eval_matrix | yes | 2 | 0 | 17.7 | yes | pass | — | One weak cell: Swahili math, 45.4% (up from 28.6%) |
| 10_incident | yes | 3 | 0 | 22.9 | yes | pass | — | Payments spiked 278x above normal on Nov 13; others stayed flat |
| 11_forest_meta | no | 3 | 0 | — | yes | pass | no_text_overlap | Pooled OR 0.75 (0.67–0.84) clears 1.0; COAST-3, PLAINS-5 cross it |
| 12_survival_km | yes | 2 | 0 | 20.3 | yes | pass | — | Combination delays progression: median 24 vs 18 months |
| 13_trap_overlapping_ci | yes | 3 | 0 | 21.5 | yes | pass | — | cand_b leads by 0.6 F1 pts, within seed noise: not ship-ready |
| 14_trap_outlier_sensor | no | 3 | 0 | — | yes | pass | no_text_struck_by_lines | Yield rises with temperature, then plateaus near 84% |
| 15_edit_switch_baseline | yes | 2 | 0 | 18.3 | yes | pass | — | cache_b adds +31% throughput over control_v2 (812 vs 620 req/s) |
| h06_enzyme_michaelis | yes | 2 | 0 | 13.6 | no | pass | — | E142A shifts Km, Vmax preserved |
| h07_cohort_attrition | no | 3 | 0 | — | yes | pass | no_text_clipped | 22.5% of screened patients complete the 12-week endpoint
(largest drop: 720 excluded at age/diagnosis) |
| h08_trap_overlap_clinical | yes | 3 | 0 | 19.9 | yes | pass | — | Arms overlap heavily: 2.7 pg/mL gap vs ~15 pg/mL spread |
| h09_trap_bad_batch | yes | 2 | 0 | 18.0 | no | pass | — | Treated vs control: consistent separation on 4 valid plates |
| h10_edit_highlight_subset | yes | 2 | 0 | 13.9 | no | pass | — | TiN-3 and BN-6 exceed the 5.0% drift limit |
| h11_chrome_trace_build | yes | 3 | 0 | 18.7 | yes | pass | — | lto_link alone takes 51.8 s, 44% of the build |
| h12_hyperfine_within_noise | yes | 1 | 0 | 14.6 | yes | pass | — | Candidate is 7.4 ms faster on average, within noise
(s.d. ≈ 19 ms) |
| h13_narrow_ide_sidebar | yes | 1 | 0 | 13.2 | yes | pass | — | Test-suite duration, 80 runs each |
| h14_repair_boxplot_claim | no | 3 | 0 | — | — | pass | script_runs, one_figure_saved |  |
| h15_repair_multipanel_ci | no | 3 | 0 | — | — | pass | script_runs, one_figure_saved |  |
| h1_survey | yes | 1 | 0 | 13.6 | yes | pass | — | Support is lowest at 42% satisfied, clearly below most peers |
| h2_spectra | yes | 1 | 0 | 16.7 | yes | pass | — | 400 °C anneal shifts the peak +25 nm; 200 °C ≈ no shift |
| h3_wait_times | yes | 1 | 0 | 16.2 | no | pass | — | South is slower only for triage levels 3–5 |
| h4_scaling | yes | 3 | 0 | 28.0 | no | pass | — | Mixture-of-experts loss falls fastest with compute |
| h5_budget | yes | 3 | 0 | 16.6 | yes | pass | — | Libraries took the biggest cut (−18%); Housing grew most (+14%) |
| pt01_volcano_omics | yes | 3 | 0 | 28.7 | no | pass | — | Volcano: 3 of 120 genes pass /log2FC/ ≥ 1.5, p < 0.01 |
| pt02_raman_peaks | no | 3 | 0 | — | no | pass | no_text_struck_by_lines |  |
| pt03_arrhenius_kinetics | yes | 1 | 0 | 13.9 | no | pass | — | Arrhenius fits: Pt is faster across 500–625 K |
| pt04_rl_seed_curves | yes | 1 | 0 | 15.4 | yes | pass | — | Mean ± 1 SD, 6 seeds |
| pt05_alloy_replicates | yes | 1 | 0 | 12.6 | no | pass | — | T6 clears 420 MPa on all 8 coupons; T6-aged misses on 2 |
| pt06_ocean_ph_trend | yes | 3 | 0 | 25.3 | yes | pass | — | Southern Ocean acidifies fastest, losing 0.051 pH in 20 years |
| pt07_trap_no_speedup | yes | 2 | 0 | 19.1 | yes | pass | — | No clear speedup: v2 is 2.8 ms faster, within noise
(95% CI of difference ±12 ms) |
| pt08_trap_simpson | yes | 1 | 0 | 12.7 | no | pass | — | Treatment looks worse overall, but is better within each severity |
| pt09_trap_small_n | yes | 2 | 0 | 11.6 | no | pass | — | Replicates overlap heavily; pilot, n = 3 per group |
| pt10_trap_near_zero_pct | yes | 2 | 0 | 12.8 | yes | pass | — | Line-C rose from 0.02% to 0.14%; other lines flat |
| pt11_trap_truncated_bait | yes | 2 | 0 | 13.5 | no | pass | — | Success rate rose in all four regions after v4.2 |
| pt12_trap_missing_control | yes | 1 | 0 | 16.1 | no | pass | — | Treated and placebo improved about equally |
| pt13_edit_log_scale | yes | 2 | 0 | 13.5 | yes | pass | — | CMP-C is 181 ng/mL at 24 h, above the 50 ng/mL floor |
| pt14_edit_add_uncertainty | yes | 2 | 0 | 11.9 | yes | pass | — | High dose is 63% above control (mean ± 95% CI, n = 7) |
| pt15_edit_fix_units | yes | 2 | 0 | 12.0 | yes | pass | — | Board-D draws 1.49 W under load, 1.63 W less than Board-A (3.12 W) |
| pt16_hyperfine_diff | yes | 1 | 0 | 11.6 | no | pass | — | Branch speeds up JSON only; YAML unchanged |
| pt17_pytest_regression | yes | 3 | 0 | 20.4 | yes | pass | — | search_query regressed +42%; others within ±4% |
| pt18_ci_pipeline_timeline | yes | 1 | 0 | 11.8 | yes | pass | — | integration-shard-3 (585 s) holds package-artifacts back |
| pt19_k6_latency_deploy | yes | 3 | 0 | 23.3 | yes | pass | — | p99 hit 796 ms after deploy, over the 500 ms SLA |
| pt20_bundle_waterfall | yes | 3 | 0 | 20.0 | yes | pass | — | 482.0 to 722.4 KB: date-locale-pack adds 214.2 |
| pt21_llm_pareto_frontier | no | 3 | 0 | — | yes | pass | no_text_struck_by_lines | 3 of 10 configs are Pareto-optimal; 7 are dominated |
| pt22_signup_funnel | no | 3 | 0 | — | yes | pass | no_text_overlap | Email verification loses 46% of signups |
| pt23_memory_soak_leak | no | 3 | 0 | — | yes | pass | no_text_struck_by_lines | worker-ingest leaks ~18 MB/h; the other workers are flat |
| pt24_narrow_phone_alert | no | 3 | 0 | — | yes | pass | no_text_struck_by_lines, no_text_clipped | Only eu-west spiked (14.3%); rollback fixed it |
| pt25_slide_quarterly_perf | yes | 3 | 0 | 17.7 | yes | pass | — | Edge caching cut Asia-Pacific p95 latency from 312.4 to 193.2 ms |
| pt26_dark_dashboard_card | yes | 1 | 0 | 15.2 | no | pass | — | Hit rate |
| pt27_terminal_only_bench | yes | 1 | 0 | 14.4 | no | pass | — |  |
| pt28_repair_ablation_bars | yes | 2 | 0 | 18.5 | yes | pass | — | Removing query rewrite costs 5.5 F1 points |
| pt29_repair_jet_heatmap | yes | 2 | 0 | 13.2 | yes | pass | — | Accuracy is 73.2%; search tickets are misrouted
to infra most (46 of 201) |
| pt30_repair_line_struck | no | 3 | 0 | — | — | pass | script_runs, one_figure_saved |  |
