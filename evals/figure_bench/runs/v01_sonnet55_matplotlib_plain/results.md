# figure-bench results: v01_sonnet55_matplotlib_plain (matplotlib-plain arm)

- Passed: **21 / 60** (9 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 36 / 60
- Reply delivers the figure (<= 60 words of prose): 60 / 60 replies (0 not provided)
- Time to pass: median 14.0 s, total 309.4 s
- Core tasks: {'tasks': 45, 'passed': 14, 'passed_first_try': 5, 'answers_correct': 27, 'replies_deliver': 45, 'median_seconds_to_pass': 14.9}
- Held-out tasks: {'tasks': 15, 'passed': 7, 'passed_first_try': 4, 'answers_correct': 9, 'replies_deliver': 15, 'median_seconds_to_pass': 14.0}
- Neutral audit, first submission: {'saved': '23/60', 'clean': '9/60', 'text_legible': '13/23', 'no_text_overlap': '21/23', 'no_text_struck_by_lines': '18/23', 'text_well_formed': '17/23', 'no_text_clipped': '22/23', 'headline_has_number': '17/23', 'headline_correct': '11/23', 'reply_correct': '39/60', 'uncertainty_named': '8/11', 'median_min_text_px': 12.2, 'with_legend': 11}
- Neutral audit, final submission: {'saved': '60/60', 'clean': '21/60', 'text_legible': '28/60', 'no_text_overlap': '55/60', 'no_text_struck_by_lines': '49/60', 'text_well_formed': '49/60', 'no_text_clipped': '57/60', 'headline_has_number': '49/60', 'headline_correct': '36/60', 'reply_correct': '39/60', 'uncertainty_named': '24/33', 'median_min_text_px': 10.9, 'with_legend': 26}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | no | 2 | 0 | — | yes | pass | no_text_struck_by_lines, text_well_formed, no_text_clipped | Grey dots: 5 seeds. Colored: mean ± 95% CI. Labels: change vs full model in accuracy, p50 latency. |
| 02_ab_latency | no | 2 | 0 | — | yes | pass | text_well_formed | New flow median change: -83 ms (95% CI -112 to -53) |
| 03_dose_response | no | 2 | 0 | — | no | pass | text_legible | Dose–response: replicates (dots) and Hill fits (lines) |
| 04_battery_fade | no | 1 | 0 | — | yes | pass | text_legible | Cell VC-3 excluded from the comparison (crimping defect; fails after cycle 200). |
| 05_retrofit | no | 1 | 0 | — | yes | pass | text_well_formed, no_text_clipped | Avg weekday kWh, after vs before 16 Jul 2026. Gym outage days excluded. |
| 06_energy_mix | no | 2 | 0 | — | yes | pass | text_legible | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | no | 2 | 0 | — | no | pass | text_legible, no_text_struck_by_lines, text_well_formed | p53 targets switch on with the drug; housekeeping stays flat |
| 08_hall_petch | yes | 1 | 0 | 13.4 | no | pass | — | Hall–Petch fits by alloy (Cu-Zn highlighted) |
| 09_eval_matrix | no | 1 | 0 | — | yes | pass | text_legible | Swahili improved most, but Swahili math (45%) is the one bad combination |
| 10_incident | no | 1 | 0 | — | no | pass | text_legible, no_text_struck_by_lines | Only payments spiked; the other four services stayed near their normal rates |
| 11_forest_meta | no | 2 | 0 | — | yes | pass | text_legible | Extended prophylaxis cuts thromboembolism odds ~25%: pooled OR 0.75 (0.67–0.84)
COAST-3 and PLAINS-5 (orange) cross 1.0 alone |
| 12_survival_km | no | 2 | 0 | — | yes | pass | text_legible | Combination extends median PFS by 7.1 months |
| 13_trap_overlapping_ci | no | 2 | 0 | — | no | pass | no_text_struck_by_lines | cand_b's lead over baseline is within seed noise
(mean ± 95% CI, dots = 5 seeds) |
| 14_trap_outlier_sensor | no | 2 | 0 | — | yes | pass | text_legible, no_text_struck_by_lines | Hour 19 excluded (thermocouple read 999.9 °C, sensor fault). |
| 15_edit_switch_baseline | no | 2 | 0 | — | yes | pass | text_legible | cache_b delivers 31% more throughput than control_v2 |
| h06_enzyme_michaelis | yes | 2 | 0 | 16.0 | no | pass | — | E142A raises Km but leaves Vmax intact |
| h07_cohort_attrition | no | 2 | 0 | — | yes | pass | text_legible | 540 of 2,400 patients (22.5%) reach the 12-week endpoint
Largest drop (red bar) highlighted; text shows exclusions and main reason per gate |
| h08_trap_overlap_clinical | no | 1 | 0 | — | yes | pass | text_well_formed | Arms overlap heavily: 150 mg vs 50 mg difference -2.7 pg/mL
(95% CI about -13 to 7, includes 0) |
| h09_trap_bad_batch | no | 2 | 0 | — | yes | pass | text_legible | Treated vs control, P1–P3, P5: 0.67 vs 0.41 OD (~1.6×) |
| h10_edit_highlight_subset | no | 2 | 0 | — | no | pass | text_legible | Only TiN-3 and BN-6 exceed the 5.0% drift limit |
| h11_chrome_trace_build | no | 1 | 0 | — | no | pass | text_legible | Release build timeline: serial LTO link dominates, not codegen |
| h12_hyperfine_within_noise | yes | 1 | 0 | 14.0 | yes | pass | — | SIMD candidate is not distinguishable from baseline
mean diff 7.4 ms vs. standard error 5.3 ms (t = 1.4) |
| h13_narrow_ide_sidebar | yes | 2 | 0 | 12.9 | yes | pass | — | Parallel tests cut durations, 80 runs each |
| h14_repair_boxplot_claim | yes | 1 | 0 | 12.0 | yes | pass | — | ap-northeast median is 141 ms,
3.0x us-east (48 ms) |
| h15_repair_multipanel_ci | yes | 1 | 0 | 14.0 | yes | pass | — | Cosine warmup overtakes baseline at epoch 6;
+5.4 pts accuracy by epoch 25 |
| h1_survey | no | 2 | 0 | — | yes | pass | text_legible | Support is least satisfied at 42% |
| h2_spectra | yes | 2 | 0 | 16.6 | yes | pass | — | 400 °C anneal red-shifts the peak ~25 nm; 200 °C does not |
| h3_wait_times | no | 2 | 0 | — | no | pass | text_legible | Dots = median; bars = interquartile range. October. |
| h4_scaling | yes | 1 | 0 | 13.9 | no | pass | — | Mixture-of-experts scales best: steepest loss–compute slope |
| h5_budget | no | 1 | 0 | — | no | pass | text_legible, text_well_formed | Budget change by department, FY2025 to FY2026 |
| pt01_volcano_omics | no | 1 | 0 | — | no | pass | text_legible, no_text_struck_by_lines | Stimulated macrophage RNA-seq: 3 of 120 genes pass both cutoffs |
| pt02_raman_peaks | no | 1 | 0 | — | yes | pass | text_legible, no_text_struck_by_lines | G band shifts +16 cm⁻¹ after 600 °C anneal (+8 at 350 °C) |
| pt03_arrhenius_kinetics | yes | 1 | 0 | 15.7 | no | pass | — | Arrhenius plot, 500–625 K (3 replicates per temperature) |
| pt04_rl_seed_curves | no | 2 | 0 | — | yes | pass | text_legible, no_text_clipped | SAC-tuned leads at 100k: every seed beats every TD3/PPO seed |
| pt05_alloy_replicates | yes | 2 | 0 | 11.4 | no | pass | — | Individual coupons vs 420 MPa spec (red X = below; bar = mean) |
| pt06_ocean_ph_trend | no | 3 | 0 | — | yes | pass | text_legible, text_well_formed | Southern Ocean is acidifying fastest: -0.026 pH/decade (-0.05 over 20 years) |
| pt07_trap_no_speedup | yes | 1 | 0 | 16.5 | no | pass | — | solver_v2 is not measurably faster than solver_v1 |
| pt08_trap_simpson | no | 2 | 0 | — | no | pass | text_legible | Treatment looks worse overall only because it was given to sicker patients
Within each severity group, treatment is not worse |
| pt09_trap_small_n | yes | 2 | 0 | 12.3 | yes | pass | — | Mean +27%, but replicates overlap (n=3 per group) |
| pt10_trap_near_zero_pct | no | 2 | 0 | — | yes | pass | text_legible | Line-C rose from 0.02% to 0.14% defect rate; other lines are flat
(the '+600%' is a tiny base: 10 → 70 defects) |
| pt11_trap_truncated_bait | yes | 2 | 0 | 17.4 | yes | pass | — | v4.2 raised success rate in every region (overall 97.4% → 98.6%) |
| pt12_trap_missing_control | no | 1 | 0 | — | no | pass | text_well_formed | Placebo improved almost as much as treatment |
| pt13_edit_log_scale | no | 2 | 0 | — | yes | pass | text_legible, no_text_struck_by_lines | CMP-C stays above the 50 ng/mL floor at 24 h (181 ng/mL) |
| pt14_edit_add_uncertainty | yes | 2 | 0 | 15.6 | yes | pass | — | High dose raises secretion 1.63× over control (+123 pg/mL) |
| pt15_edit_fix_units | no | 2 | 0 | — | yes | pass | text_legible | Board-D |
| pt16_hyperfine_diff | yes | 1 | 0 | 10.9 | no | pass | — | Branch vs main (20 runs each; dots = individual runs) |
| pt17_pytest_regression | no | 1 | 0 | — | no | pass | text_legible, text_well_formed | Only one endpoint regressed; the other five are within noise |
| pt18_ci_pipeline_timeline | no | 3 | 0 | — | yes | pass | text_legible, no_text_overlap | integration-shard-3 (585 s) gates package-artifacts; other jobs idle 325–470 s |
| pt19_k6_latency_deploy | no | 2 | 0 | — | no | pass | text_legible, no_text_overlap, no_text_struck_by_lines | After the deploy, p99 breaches the SLA while p50 stays flat |
| pt20_bundle_waterfall | no | 1 | 0 | — | yes | pass | text_legible, no_text_overlap, text_well_formed | dist/app.bundle.js grew 240.4 kB (+50%); date-locale-pack is 89% of it |
| pt21_llm_pareto_frontier | no | 2 | 0 | — | no | pass | text_legible, no_text_overlap | Accuracy vs cost and latency: Pareto frontier of 10 serving configs |
| pt22_signup_funnel | no | 2 | 0 | — | yes | pass | text_legible, text_well_formed | Email verification loses 46% of users, mostly from delayed verification emails |
| pt23_memory_soak_leak | no | 1 | 0 | — | yes | pass | text_legible, no_text_struck_by_lines | worker-ingest leaks ~18.0 MB/hour; hits 2 GB OOM cap near hour 90 |
| pt24_narrow_phone_alert | no | 1 | 0 | — | no | pass | no_text_overlap, no_text_struck_by_lines | Isolated to eu-west; rollback fixed it
Below 1% by 18:33 |
| pt25_slide_quarterly_perf | yes | 2 | 0 | 14.9 | yes | pass | — | Edge caching cut asia-pacific latency 38% and lifted throughput 44% (Q1→Q4) |
| pt26_dark_dashboard_card | yes | 3 | 0 | 21.8 | no | pass | — | Hit rate |
| pt27_terminal_only_bench | yes | 2 | 0 | 19.5 | no | pass | — |  |
| pt28_repair_ablation_bars | yes | 1 | 0 | 12.9 | yes | pass | — | Removing query rewrite costs 5.5 F1 points |
| pt29_repair_jet_heatmap | yes | 2 | 0 | 12.7 | yes | pass | — | Accuracy is 73.2%, not 96.4%; search→infra is the top misroute |
| pt30_repair_line_struck | yes | 2 | 0 | 15.0 | yes | pass | — | v2.0 peaks at 4,820 req/s, +48% over v1.0 |
