# figure-bench results: v01_sonnet55_mintfig (mintfig arm)

- Passed: **56 / 60** (33 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 52 / 60
- Reply delivers the figure (<= 60 words of prose): 57 / 60 replies (0 not provided)
- Time to pass: median 13.2 s, total 773.0 s
- Core tasks: {'tasks': 45, 'passed': 42, 'passed_first_try': 22, 'answers_correct': 37, 'replies_deliver': 42, 'median_seconds_to_pass': 13.4}
- Held-out tasks: {'tasks': 15, 'passed': 14, 'passed_first_try': 11, 'answers_correct': 15, 'replies_deliver': 15, 'median_seconds_to_pass': 12.0}
- Neutral audit, first submission: {'saved': '35/60', 'clean': '35/60', 'text_legible': '35/35', 'no_text_overlap': '35/35', 'no_text_struck_by_lines': '35/35', 'text_well_formed': '35/35', 'no_text_clipped': '35/35', 'headline_has_number': '35/35', 'headline_correct': '33/35', 'reply_correct': '53/60', 'uncertainty_named': '19/22', 'median_min_text_px': 12.3, 'with_legend': 3}
- Neutral audit, final submission: {'saved': '57/60', 'clean': '57/60', 'text_legible': '57/57', 'no_text_overlap': '57/57', 'no_text_struck_by_lines': '57/57', 'text_well_formed': '57/57', 'no_text_clipped': '57/57', 'headline_has_number': '57/57', 'headline_correct': '53/57', 'reply_correct': '53/60', 'uncertainty_named': '29/33', 'median_min_text_px': 12.3, 'with_legend': 3}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | yes | 1 | 0 | 13.6 | yes | pass | — | The reranker adds 1.6 points for 121 ms; the bigger encoder's 0.5 points is within seed noise |
| 02_ab_latency | yes | 1 | 0 | 12.0 | yes | pass | — | The new flow is faster: median 341 ms vs 424 ms, and the slow tail shrank too |
| 03_dose_response | yes | 1 | 0 | 15.6 | yes | pass | — | CPD-7 is the most potent (IC50 ≈ 12 nM); CPD-4 never reaches 50% inhibition |
| 04_battery_fade | yes | 1 | 0 | 16.7 | yes | pass | — | Baseline cells reach 80% retention near cycle 460; FEC lasts ~230 cycles longer, VC ~150 |
| 05_retrofit | yes | 1 | 0 | 13.1 | yes | pass | — | The retrofit cut daily use 18% at the Library and 28% at the Lab annex; the Gym barely moved (−3%) |
| 06_energy_mix | yes | 2 | 0 | 15.5 | yes | pass | — | Renewables supplied 34% of the region's electricity in 2025, excluding biomass |
| 07_gene_change | yes | 1 | 0 | 16.4 | yes | pass | — | The drug switched on the p53 programme (median 2.4×, CDKN1A 7×) and shut down proliferation (0.55×); housekeeping stays flat |
| 08_hall_petch | yes | 3 | 0 | 21.9 | yes | pass | — | Cu-Zn follows Hall–Petch with a slope of 327 MPa·µm½ (R² 0.94) |
| 09_eval_matrix | no | 3 | 0 | — | — | fail | script_runs, one_figure_saved |  |
| 10_incident | yes | 1 | 0 | 13.1 | yes | pass | — | Payments spiked on Nov 13 to 2.1% errors, ~278× its normal rate |
| 11_forest_meta | yes | 2 | 0 | 12.2 | yes | pass | — | Pooled odds ratio is 0.75 (95% CI 0.67–0.84), clearing 1.0; COAST-3 and PLAINS-5 cross it |
| 12_survival_km | yes | 1 | 0 | 14.8 | yes | pass | — | Combination therapy delays median progression-free survival by 6 months (18 to 24) |
| 13_trap_overlapping_ci | yes | 2 | 0 | 12.4 | yes | pass | — | cand_b leads baseline by 0.6 F1 points, but all intervals overlap: not enough evidence to ship |
| 14_trap_outlier_sensor | yes | 2 | 0 | 14.9 | yes | pass | — | Yield climbs from 65% to a peak of 84.7% at 241 °C, flattening above ~220 °C |
| 15_edit_switch_baseline | yes | 2 | 0 | 12.5 | yes | pass | — | cache_b delivers 812 req/s, 31% (192 req/s) more than control_v2 |
| h06_enzyme_michaelis | yes | 2 | 0 | 19.4 | yes | pass | — | E142A mainly weakens binding: Km rises 4-fold (5.8 to 21.2 µM) while Vmax stays near 48 µM/min |
| h07_cohort_attrition | no | 3 | 0 | — | yes | pass | no_warnings | Only 540 of 2,400 patients (22.5%) complete the 12-week endpoint; the two biggest drops come before consent |
| h08_trap_overlap_clinical | yes | 1 | 0 | 9.1 | yes | pass | — | The 3 pg/mL mean gap between doses is small next to patient-to-patient spread |
| h09_trap_bad_batch | yes | 1 | 0 | 13.9 | yes | pass | — | Treated wells read about 0.26 OD higher than control (0.67 vs 0.41) on the four valid plates |
| h10_edit_highlight_subset | yes | 2 | 0 | 12.9 | yes | pass | — | TiN-3 and BN-6 fail the 5.0% limit, by 2.8 and 1.4 points |
| h11_chrome_trace_build | yes | 1 | 0 | 8.1 | yes | pass | — | The single-threaded lto_link takes 51.8 s, 44% of the 118.4 s build, so more codegen threads won't help |
| h12_hyperfine_within_noise | yes | 1 | 0 | 9.9 | yes | pass | — | The SIMD candidate is 7 ms faster on average, well within run-to-run noise (±19 ms) |
| h13_narrow_ide_sidebar | yes | 1 | 0 | 10.1 | yes | pass | — | 8-worker parallelism cuts median test time from 188 s to 78 s |
| h14_repair_boxplot_claim | yes | 1 | 0 | 10.5 | yes | pass | — | ap-northeast median latency is 141 ms, about 3× us-east (48 ms) |
| h15_repair_multipanel_ci | yes | 1 | 0 | 14.8 | yes | pass | — | Cosine warmup beats SGD on loss from epoch 6 and ends 5.4 points more accurate (89.0% vs 83.7%) |
| h1_survey | yes | 1 | 0 | 14.7 | yes | pass | — | Support is least satisfied at 42%, but its range overlaps Sales and Operations, so it is the bottom of a spread |
| h2_spectra | yes | 1 | 0 | 11.9 | yes | pass | — | The 400 °C anneal shifts the absorption peak by 25 nm (520 to 545 nm); 200 °C moves it only 5 nm |
| h3_wait_times | yes | 1 | 0 | 13.9 | yes | pass | — | South is slower only for less urgent patients: levels 3–5 wait 10–45 min longer, levels 1–2 match North |
| h4_scaling | yes | 1 | 0 | 11.6 | yes | pass | — | Mixture-of-experts scales best: loss ∝ compute^−0.063, vs −0.050 dense and −0.031 recurrent |
| h5_budget | yes | 2 | 0 | 12.1 | yes | pass | — | Libraries took the biggest cut (−18%), Parks fell 11%, Housing grew 14%; the rest are within ±5% |
| pt01_volcano_omics | yes | 1 | 0 | 13.4 | yes | pass | — | Only 3 of 120 genes clear both cutoffs; CXCL10 is the strongest mover at +3.42 log2FC |
| pt02_raman_peaks | yes | 1 | 0 | 14.0 | yes | pass | — | The 600 °C anneal shifts the G-band up 16 cm⁻¹ (1578 → 1594); 350 °C moves it 8 cm⁻¹ |
| pt03_arrhenius_kinetics | yes | 1 | 0 | 14.5 | yes | pass | — | Cat-Pt has the lower barrier (53 vs 85 kJ/mol); Cat-Ni closes the gap from 13× to 3× but never catches up |
| pt04_rl_seed_curves | yes | 2 | 0 | 22.5 | yes | pass | — | SAC-tuned leads by 89 points over TD3-clip and 134 over PPO-base at 100k steps, beyond seed spread |
| pt05_alloy_replicates | yes | 2 | 0 | 12.1 | no | pass | — | T6-aged can't qualify: 2 of 8 coupons fall below 420 MPa, while all 8 T6 coupons clear it |
| pt06_ocean_ph_trend | yes | 1 | 0 | 13.1 | yes | pass | — | Southern Ocean is acidifying fastest: pH falls 0.026 per decade, 0.051 over 20 years |
| pt07_trap_no_speedup | yes | 2 | 0 | 21.5 | yes | pass | — | solver_v2 is 2.8 ms faster on average, but trial noise is larger, so a real speedup is not shown |
| pt08_trap_simpson | yes | 1 | 0 | 11.0 | no | pass | — | Treatment recovers more patients in both severity groups; it only looks worse overall because 86% of its patients are severe |
| pt09_trap_small_n | yes | 2 | 0 | 12.3 | yes | pass | — | Inhibitor mean is 27% higher (1.28 vs 1.01), but n = 3 per arm and the ranges overlap |
| pt10_trap_near_zero_pct | yes | 2 | 0 | 13.3 | yes | pass | — | Line-C defects rose from 10 to 70 per 50,000 units (0.02% to 0.14%); the other lines barely moved |
| pt11_trap_truncated_bait | yes | 2 | 0 | 13.0 | yes | pass | — | v4.2 cut failed requests from ~2.6% to ~1.4% — nearly half — in every region |
| pt12_trap_missing_control | yes | 1 | 0 | 12.9 | no | pass | — | Placebo patients improved almost as much (−8.4 vs −9.0 points), so most of the 15% gain isn't the treatment |
| pt13_edit_log_scale | yes | 3 | 0 | 15.3 | yes | pass | — | Only CMP-C stays above the 50 ng/mL floor at 24 h, at 181 ng/mL |
| pt14_edit_add_uncertainty | yes | 2 | 0 | 14.0 | no | pass | — | High dose lifts secretion 1.6× over control, far outside the 95% CI |
| pt15_edit_fix_units | yes | 3 | 0 | 15.1 | yes | pass | — | Board-D cuts peak load power to 1.49 W (−52% vs Board-A) |
| pt16_hyperfine_diff | yes | 1 | 0 | 9.7 | yes | pass | — | The branch cuts JSON parsing by 31%, far beyond noise; YAML is unchanged (0.1%) |
| pt17_pytest_regression | yes | 1 | 0 | 15.5 | yes | pass | — | test_search_query regressed 42% in mean latency (18.7 → 26.5 ms); the other five stay within ±4% |
| pt18_ci_pipeline_timeline | yes | 1 | 0 | 11.5 | yes | pass | — | integration-shard-3 runs 585 s and holds package-artifacts back by 325 s |
| pt19_k6_latency_deploy | no | 3 | 0 | — | — | fail | script_runs, one_figure_saved |  |
| pt20_bundle_waterfall | yes | 1 | 0 | 12.8 | yes | pass | — | One dependency, date-locale-pack, adds 214 kB of the 240 kB bundle growth |
| pt21_llm_pareto_frontier | yes | 2 | 0 | 17.6 | yes | pass | — | Only 3 of 10 configs are Pareto-optimal; the other 7 are strictly dominated |
| pt22_signup_funnel | no | 3 | 0 | — | — | fail | script_runs, one_figure_saved |  |
| pt23_memory_soak_leak | yes | 1 | 0 | 14.8 | yes | pass | — | worker-ingest leaks 18 MB/h and will hit the 2,048 MB OOM cap at about hour 90, 42 h after this soak ends |
| pt24_narrow_phone_alert | yes | 3 | 0 | 17.8 | yes | pass | — | Only eu-west broke, peaking at 14.3%; the 18:28 rollback brought it under 1% by 18:33 |
| pt25_slide_quarterly_perf | yes | 2 | 0 | 13.0 | yes | pass | — | Edge caching cut asia-pacific p95 latency 38% (312 to 193 ms) and lifted throughput 44% |
| pt26_dark_dashboard_card | yes | 1 | 0 | 11.5 | yes | pass | — | S3-FIFO hits 89.4%, 4 points above TinyLFU, at under half its eviction CPU |
| pt27_terminal_only_bench | yes | 1 | 0 | 13.3 | no | pass | — | flatwire decodes 2x faster than proto-lite but its payload is 54% larger |
| pt28_repair_ablation_bars | yes | 1 | 0 | 12.6 | yes | pass | — | Removing query rewrite costs 5.5 F1 points; BM25 alone loses 9.7 |
| pt29_repair_jet_heatmap | yes | 2 | 0 | 16.6 | yes | pass | — | The router is 73.2% accurate, and 23% of search tickets are misrouted to infra |
| pt30_repair_line_struck | yes | 2 | 0 | 10.7 | yes | pass | — | v2.0 peaks at 4,820 req/s at 64 workers, 48% above v1.0 |
