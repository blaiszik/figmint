# figure-bench results: v01_100_sonnet55_mintfig (mintfig arm)

- Passed: **98 / 100** (75 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 95 / 100
- Reply delivers the figure (<= 60 words of prose): 100 / 100 replies (0 not provided)
- Time to pass: median 11.6 s, mean 13.1 s, p90 19.6 s, total 1281.3 s (first submit median 10.63 s, render median 0.631 s)
- Core tasks: {'tasks': 75, 'passed': 74, 'passed_first_try': 57, 'answers_correct': 71, 'replies_deliver': 75, 'median_seconds_to_pass': 11.7, 'median_seconds_total': 11.7, 'mean_seconds_to_pass': 12.9, 'p90_seconds_to_pass': 19.2}
- Held-out tasks: {'tasks': 25, 'passed': 24, 'passed_first_try': 18, 'answers_correct': 24, 'replies_deliver': 25, 'median_seconds_to_pass': 11.4, 'median_seconds_total': 11.6, 'mean_seconds_to_pass': 13.7, 'p90_seconds_to_pass': 19.3}
- Neutral audit, first submission: {'saved': '87/100', 'clean': '87/100', 'text_legible': '87/87', 'no_text_overlap': '87/87', 'no_text_struck_by_lines': '87/87', 'text_well_formed': '87/87', 'no_text_clipped': '87/87', 'headline_has_number': '87/87', 'headline_correct': '85/87', 'reply_correct': '93/100', 'uncertainty_named': '48/50', 'median_min_text_px': 12.3, 'with_legend': 2}
- Neutral audit, final submission: {'saved': '100/100', 'clean': '100/100', 'text_legible': '100/100', 'no_text_overlap': '100/100', 'no_text_struck_by_lines': '100/100', 'text_well_formed': '100/100', 'no_text_clipped': '100/100', 'headline_has_number': '100/100', 'headline_correct': '97/100', 'reply_correct': '94/100', 'uncertainty_named': '55/57', 'median_min_text_px': 12.3, 'with_legend': 2}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Total (s) | Render (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | ---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | yes | 1 | 0 | 15.5 | 15.5 | 0.741 | yes | pass | — | The reranker adds 1.6 points for 121 ms; the bigger encoder adds 0.5, within noise, for 60 ms |
| 02_ab_latency | yes | 1 | 0 | 11.4 | 11.4 | 0.738 | yes | pass | — | The new flow is faster: median 341 ms vs 424 ms, and the slow tail shrank too |
| 03_dose_response | yes | 1 | 0 | 13.9 | 13.9 | 0.633 | yes | pass | — | CPD-7 reaches 50% inhibition at ~12 nM, 13× more potent than CPD-2; CPD-4 never gets there |
| 04_battery_fade | yes | 1 | 0 | 14.8 | 14.8 | 1.041 | yes | pass | — | Baseline cells reach 80% retention at about cycle 460; FEC lasts to ~690 and VC to ~605 |
| 05_retrofit | yes | 1 | 0 | 14.7 | 14.7 | 0.962 | yes | pass | — | The retrofit cut daily use 18% at the Library and 28% at the Lab annex; the Gym barely moved (−3%) |
| 06_energy_mix | yes | 1 | 0 | 14.8 | 14.8 | 1.138 | yes | pass | — | Renewables supplied 34% of the region's electricity in 2025, excluding biomass |
| 07_gene_change | yes | 2 | 0 | 26.6 | 26.6 | 1.247 | yes | pass | — | The drug switched on the p53 programme: targets rose 2.5× (median), led by CDKN1A at 7×, while proliferation fell |
| 08_hall_petch | yes | 3 | 0 | 21.2 | 21.2 | 2.063 | yes | pass | — | Cu-Zn follows Hall–Petch with a slope of 327 MPa·µm½ (R² 0.94); Al-Mg fits least well (R² 0.81) |
| 09_eval_matrix | no | 3 | 0 | — | 18.7 | 1.83 | yes | pass | no_warnings | Swahili improved but is still the weakest language, mostly because of one cell: math at 45% |
| 10_incident | yes | 1 | 0 | 10.4 | 10.4 | 0.77 | yes | pass | — | Payments spiked to 2.1% on 13 Nov, about 280× its normal rate; no other service moved |
| 11_forest_meta | yes | 1 | 0 | 8.8 | 8.8 | 0.648 | yes | pass | — | Extended prophylaxis cuts thrombo-embolism odds 25% (pooled OR 0.75, CI 0.67–0.84); two small trials cross 1.0 |
| 12_survival_km | yes | 1 | 0 | 13.5 | 13.5 | 0.653 | yes | pass | — | The combination arm delays median progression-free survival by 6 months (18 to 24) |
| 13_trap_overlapping_ci | yes | 1 | 0 | 9.0 | 9.0 | 0.544 | yes | pass | — | cand_b's +0.6 F1 lead over baseline is within seed noise, so it is not ready to ship on this evidence |
| 14_trap_outlier_sensor | yes | 1 | 0 | 9.1 | 9.1 | 0.554 | yes | pass | — | Yield climbs from 65% to a peak of 84.7% at 241 °C, flattening above ~228 °C |
| 15_edit_switch_baseline | yes | 1 | 0 | 8.7 | 8.7 | 0.626 | yes | pass | — | cache_b adds 192 req/s (+31%) over current production control_v2 |
| 16_calibration_reliability | yes | 1 | 0 | 14.0 | 14.0 | 0.731 | no | pass | — | Temperature scaling cuts ECE 86%, from 0.118 to 0.017, at the same AUROC of 0.91 |
| 17_gpu_roofline_kernels | yes | 1 | 0 | 8.3 | 8.3 | 0.593 | yes | pass | — | moe_grouped_gemm reaches only 49% of its 989 TFLOP/s roof, while the other kernels reach 63–87% |
| 18_db_query_plan_tail | yes | 2 | 0 | 15.1 | 15.1 | 0.91 | yes | pass | — | The index cut orders_join p99 from 150.5 to 24.6 ms, but order_insert p99 rose from 13.2 to 20.7 ms |
| 19_trap_dual_axis_spurious | yes | 1 | 0 | 13.3 | 13.3 | 0.639 | yes | pass | — | Year-over-year, solar and avocado changes are uncorrelated (r = −0.07), so the 0.99 raw match is shared trend |
| 20_trap_survivorship_bias | yes | 1 | 0 | 12.6 | 12.6 | 0.467 | yes | pass | — | Active accounts score 83.5, but the 24 that churned scored 36.3 — all 60 average 64.6 |
| 21_edit_normalize_per_capita | yes | 1 | 0 | 11.0 | 11.0 | 0.69 | yes | pass | — | Cedar-Flats and Pine-Ridge have the highest risk, about 3× Metro-North per resident |
| 22_edit_split_confounder | yes | 1 | 0 | 11.7 | 11.7 | 0.546 | yes | pass | — | FP8 runs turn upward after 40k steps while BF16 keeps improving: 2.38 vs 2.02 at 80k |
| 23_surface_narrow_oncall | yes | 1 | 0 | 7.4 | 7.4 | 0.601 | yes | pass | — | checkout-api has 21% of its error budget left; the other three have 64% or more |
| 24_surface_html_interactive_report | yes | 1 | 0 | 12.3 | 12.3 | 0.585 | yes | pass | — | Android F1 fell 9.4 points since May, far outside eval noise; other slices moved ≤1.1 |
| 25_repair_truncated_and_rainbow | yes | 2 | 0 | 17.2 | 17.2 | 1.244 | yes | pass | — | Top-1 accuracy rose 4.8 points (+6.0%) from v1.0 to v1.3 |
| h06_enzyme_michaelis | yes | 3 | 0 | 41.7 | 41.7 | 2.084 | yes | pass | — | E142A raises Km 3.7× (to 21.3 µM) while Vmax stays near 45.2 vs 48.4 µM/min |
| h07_cohort_attrition | yes | 1 | 0 | 7.8 | 7.8 | 0.635 | yes | pass | — | Only 22.5% of screened patients (540 of 2,400) complete the 12-week endpoint; the biggest drop is at eligibility (−720) |
| h08_trap_overlap_clinical | yes | 1 | 0 | 11.1 | 11.1 | 0.63 | yes | pass | — | The 150 mg arm's 2.7 pg/mL larger mean reduction is small next to patient-to-patient spread |
| h09_trap_bad_batch | yes | 1 | 0 | 13.1 | 13.1 | 0.559 | yes | pass | — | Treated reads 1.6× control OD on the four valid plates (0.67 vs 0.41) |
| h10_edit_highlight_subset | yes | 1 | 0 | 9.3 | 9.3 | 0.644 | yes | pass | — | TiN-3 and BN-6 fail the 5.0% limit, by 2.8 and 1.4 points |
| h11_chrome_trace_build | yes | 1 | 0 | 9.2 | 9.2 | 0.512 | yes | pass | — | The serial lto_link stage takes 52 s, 44% of the 118 s build, so more codegen threads can't fix it |
| h12_hyperfine_within_noise | yes | 1 | 0 | 9.5 | 9.5 | 0.417 | yes | pass | — | The candidate's 7 ms lower mean is within run-to-run noise (s.d. ≈ 19 ms) |
| h13_narrow_ide_sidebar | yes | 1 | 0 | 10.6 | 10.6 | 0.643 | yes | pass | — | 8 parallel workers cut median test time from 188 s to 78 s |
| h14_repair_boxplot_claim | yes | 1 | 0 | 9.5 | 9.5 | 0.567 | yes | pass | — | ap-northeast median latency is 141 ms, about 3× us-east (48 ms) |
| h15_repair_multipanel_ci | yes | 1 | 0 | 13.9 | 13.9 | 0.701 | yes | pass | — | Cosine warmup overtakes baseline at epoch 6 and ends 5.4 points more accurate |
| h16_pharmacokinetics_auc | yes | 3 | 0 | 20.5 | 20.5 | 1.544 | yes | pass | — | Liposomal_IV gives 2.1× the 24 h exposure (AUC₀₋₂₄) of IR_tablet |
| h17_catalyst_selectivity_tradeoff | yes | 1 | 0 | 11.6 | 11.6 | 0.645 | yes | pass | — | In2O3-ZrO2 gives the highest single-pass yield, about 68%, despite middling selectivity |
| h18_gc_pause_tail_cdf | yes | 1 | 0 | 9.4 | 9.4 | 0.54 | yes | pass | — | JVM-G1GC pauses reach 142 ms at p99.9, 11× JVM-ZGC and 8× Go-1.23 |
| h19_distributed_scaling_eff | yes | 1 | 0 | 11.1 | 11.1 | 0.645 | yes | pass | — | At 64 nodes NCCL keeps 81% efficiency while Gloo-TCP falls to 22% |
| h1_survey | yes | 1 | 0 | 13.8 | 13.8 | 0.597 | yes | pass | — | Support is least satisfied (42%), but its interval overlaps Sales and Operations: it is the bottom of a spread |
| h20_trap_ecological_fallacy | yes | 3 | 0 | 16.1 | 16.1 | 1.466 | yes | pass | — | Within every district, more tutoring goes with lower scores (about −3 points per hour) |
| h21_trap_missing_zero_truncation | yes | 1 | 0 | 11.2 | 11.2 | 0.626 | yes | pass | — | Charger-D is about 1.7 points more efficient than Charger-A, and no unit overlaps |
| h22_edit_add_control_and_exclude_drift | yes | 1 | 0 | 9.8 | 9.8 | 0.573 | yes | pass | — | Treatment lifts response by 6.0 a.u. over sham control (18.5 vs 12.5) |
| h23_surface_terminal_ci_diff | yes | 3 | 0 | 20.2 | 20.2 | 1.576 | yes | pass | — | zstd-3 compresses to 3.42x vs 2.15x for lz4-fast, at about half the decompression speed |
| h24_surface_narrow_pr_comment | yes | 2 | 0 | 17.1 | 17.1 | 0.939 | yes | pass | — | Arena allocator cuts type_check peak memory 40%, 683 to 409 MB |
| h25_repair_ci_and_wrong_p | no | 3 | 0 | — | 28.2 | 1.761 | yes | pass | no_warnings | Variant X scores 2.3 points (+3.5%) above control, but the 95% CIs overlap |
| h2_spectra | yes | 1 | 0 | 15.2 | 15.2 | 0.552 | yes | pass | — | The 400 °C anneal shifts the absorption peak by about 21 nm; 200 °C barely moves it |
| h3_wait_times | yes | 2 | 0 | 14.2 | 14.2 | 0.942 | no | pass | — | South is slower only for less urgent patients: levels 3–5 wait longer, levels 1–2 match North |
| h4_scaling | yes | 1 | 0 | 13.6 | 13.6 | 0.592 | yes | pass | — | Mixture-of-experts scales best: loss ∝ compute^−0.063, vs −0.050 dense and −0.031 recurrent |
| h5_budget | yes | 1 | 0 | 8.7 | 8.7 | 0.604 | yes | pass | — | Libraries took the biggest cut (−18%), Parks fell 11% and Housing grew 14%; the rest is within ±5% |
| pt01_volcano_omics | yes | 1 | 0 | 15.9 | 15.9 | 0.601 | no | pass | — | CXCL10 is the strongest mover: 3 of 120 genes pass both cutoffs (/log2 FC/ ≥ 1.5, p < 0.01) |
| pt02_raman_peaks | yes | 1 | 0 | 11.7 | 11.7 | 0.673 | yes | pass | — | The 600 °C anneal shifts the G-band up 16 cm⁻¹; 350 °C already moved it 8 cm⁻¹ |
| pt03_arrhenius_kinetics | yes | 1 | 0 | 14.7 | 14.7 | 0.824 | yes | pass | — | Cat-Pt has the lower barrier (53 vs 85 kJ/mol); Cat-Ni narrows the gap from 13× to 3× but never catches up by 625 K |
| pt04_rl_seed_curves | yes | 1 | 0 | 11.7 | 11.7 | 0.619 | yes | pass | — | SAC-tuned leads at 100k steps by 89 over TD3-clip and 134 over PPO-base, far outside seed spread |
| pt05_alloy_replicates | yes | 1 | 0 | 12.5 | 12.5 | 0.597 | no | pass | — | T6-aged misses the 420 MPa spec on 2 of 8 coupons; every T6 coupon clears it |
| pt06_ocean_ph_trend | yes | 1 | 0 | 10.5 | 10.5 | 0.702 | yes | pass | — | Southern Ocean acidifies fastest: −0.026 pH per decade, −0.051 over 20 years |
| pt07_trap_no_speedup | yes | 3 | 0 | 18.8 | 18.8 | 1.682 | yes | pass | — | solver_v2 averages 2.8 ms (2%) faster, but runtimes overlap heavily across 10 trials each |
| pt08_trap_simpson | yes | 3 | 0 | 23.8 | 23.8 | 1.852 | yes | pass | — | Treatment beats control within each severity group (+5 and +12 points); the pooled 58% vs 80% is a mix effect |
| pt09_trap_small_n | yes | 1 | 0 | 9.5 | 9.5 | 0.504 | yes | pass | — | Inhibitor mean is 27% higher, but with n=3 the replicates overlap, so this pilot cannot confirm an effect |
| pt10_trap_near_zero_pct | yes | 1 | 0 | 9.9 | 9.9 | 0.615 | yes | pass | — | Line-C's +600% is real but tiny: 0.02% to 0.14% of units, still under 0.15% on every line |
| pt11_trap_truncated_bait | yes | 1 | 0 | 10.0 | 10.0 | 0.543 | yes | pass | — | Every region's success rate rose 1.1–1.3 points after v4.2 |
| pt12_trap_missing_control | yes | 3 | 0 | 21.0 | 21.0 | 1.358 | no | pass | — | Placebo patients improved as much as treated ones (14% vs 15%), so the drop is not evidence the treatment worked |
| pt13_edit_log_scale | yes | 1 | 0 | 9.2 | 9.2 | 0.577 | yes | pass | — | Only CMP-C stays above the 50 ng/mL floor at 24 h, at 181 ng/mL |
| pt14_edit_add_uncertainty | yes | 2 | 0 | 19.3 | 19.3 | 1.086 | yes | pass | — | High dose raises secretion 123 pg/mL over control (1.6×) |
| pt15_edit_fix_units | yes | 1 | 0 | 8.1 | 8.1 | 0.515 | yes | pass | — | Board-D draws 1.49 W under load (1,490 mW), 1.63 W less than Board-A |
| pt16_hyperfine_diff | yes | 2 | 0 | 14.5 | 14.5 | 0.705 | yes | pass | — | The branch speeds up JSON parsing by 31% but leaves YAML unchanged (0.1%) |
| pt17_pytest_regression | yes | 1 | 0 | 12.3 | 12.3 | 0.506 | yes | pass | — | Only search_query regressed: mean latency +42%, while the other five endpoints moved under 4% |
| pt18_ci_pipeline_timeline | yes | 1 | 0 | 9.7 | 9.7 | 0.505 | yes | pass | — | Integration shard 3 runs 585 s and holds package-artifacts back by 5+ minutes |
| pt19_k6_latency_deploy | yes | 3 | 0 | 22.9 | 22.9 | 1.362 | yes | pass | — | After the deploy, p99 latency exceeded the 500 ms SLA in all 30 minutes while p50 barely moved |
| pt20_bundle_waterfall | yes | 1 | 0 | 9.7 | 9.7 | 0.451 | yes | pass | — | One new dependency, date-locale-pack, adds 214 kB of the 240 kB bundle growth |
| pt21_llm_pareto_frontier | yes | 1 | 0 | 10.6 | 10.6 | 0.432 | yes | pass | — | Only 3 of 10 configs are Pareto-optimal; the other 7 are strictly dominated |
| pt22_signup_funnel | yes | 2 | 0 | 16.9 | 16.9 | 1.378 | yes | pass | — | Email verification loses 46% of users, the biggest drop, because verification emails arrive late |
| pt23_memory_soak_leak | yes | 3 | 0 | 21.9 | 21.9 | 1.427 | yes | pass | — | worker-ingest leaks 18 MB/hour and will hit the 2,048 MB OOM cap near hour 90, 42 hours after the soak ended |
| pt24_narrow_phone_alert | yes | 2 | 0 | 18.6 | 18.6 | 0.91 | yes | pass | — | Only eu-west broke: errors peaked at 14.3%, and the 18:28 rollback cut them below 1% by 18:33 |
| pt25_slide_quarterly_perf | yes | 1 | 0 | 8.7 | 8.7 | 0.602 | yes | pass | — | Edge caching cut asia-pacific p95 latency 38% (312 to 193 ms) and lifted throughput 44% |
| pt26_dark_dashboard_card | yes | 1 | 0 | 13.6 | 13.6 | 0.656 | yes | pass | — | S3-FIFO hits 89.4% on every trace, 4 points above TinyLFU at half the eviction CPU |
| pt27_terminal_only_bench | yes | 3 | 0 | 20.4 | 20.4 | 1.658 | yes | pass | — | flatwire decodes 2.1× faster than proto-lite, with a 54% larger payload |
| pt28_repair_ablation_bars | yes | 1 | 0 | 8.9 | 8.9 | 0.582 | yes | pass | — | Removing query rewrite costs 5.5 points of F1 versus the full pipeline |
| pt29_repair_jet_heatmap | yes | 1 | 0 | 9.4 | 9.4 | 0.592 | yes | pass | — | Ticket routing is 73.2% accurate; 46 search tickets are misrouted to infra |
| pt30_repair_line_struck | yes | 1 | 0 | 8.4 | 8.4 | 0.538 | yes | pass | — | v2.0 peaks at 4,820 req/s at concurrency 64, 48% above v1.0; v1.1 falls 19% below at 128 |
| pt31_bland_altman | yes | 1 | 0 | 13.9 | 13.9 | 0.524 | yes | pass | — | Wearable reads 1.7 points high, and error spreads about 3× wider in the hypoxic range |
| pt32_xrd_phase_shift | yes | 1 | 0 | 13.6 | 13.6 | 0.556 | yes | pass | — | 4% compressive strain shifts the (111) peak by +0.69° 2θ |
| pt33_crispr_screen_rank | yes | 1 | 0 | 11.7 | 11.7 | 0.405 | yes | pass | — | Four of 50 genes pass FDR < 0.05, led by PRMT5 at log2FC −3.45 (guide SD 0.21) |
| pt34_climate_ensemble_fan | yes | 1 | 0 | 10.6 | 10.6 | 0.558 | yes | pass | — | By 2100 the median SSP3-7.0 run is 2.6 °C warmer than SSP1-2.6 (4.3 vs 1.7 °C) |
| pt35_cache_eviction_hitrate | yes | 1 | 0 | 10.9 | 10.9 | 0.58 | yes | pass | — | At 256 MB, S3-FIFO misses 7.1 points less than LRU (18.7% vs 25.8%) |
| pt36_token_throughput_batch | yes | 3 | 0 | 18.3 | 18.3 | 1.706 | yes | pass | — | Batch 16 is the highest-throughput setting under the 200 ms TTFT SLA: 748 tok/s at 168 ms |
| pt37_flaky_ci_heatmap | yes | 1 | 0 | 10.5 | 10.5 | 0.655 | yes | pass | — | Flakiness is concentrated in auth_oauth, which climbs from 0.4% to 22.6%; other modules stay under 2.5% |
| pt38_cloud_cost_waterfall | yes | 1 | 0 | 9.0 | 9.0 | 0.441 | yes | pass | — | GPU inference drove $34.8k of the $41.2k net rise in the monthly cloud bill |
| pt39_trap_multiple_testing | yes | 2 | 0 | 15.5 | 15.5 | 1.417 | yes | pass | — | The +1.12% search_click_depth win (raw p = 0.038) fails correction: adjusted p = 0.76 |
| pt40_trap_heavy_tail_mean | yes | 1 | 0 | 8.9 | 8.9 | 0.544 | yes | pass | — | The +48% mean lift comes from 3 huge orders; the typical order is 4% lower (median $45.55 vs $47.67) |
| pt41_trap_denominator_shift | yes | 1 | 0 | 6.7 | 6.7 | 0.507 | yes | pass | — | Alerts per million requests fell 15%, from 13.0 in Jan to 11.0 in Jun |
| pt42_trap_cherry_picked_window | yes | 1 | 0 | 9.1 | 9.1 | 0.505 | yes | pass | — | Signups are flat near 100k a week; the +18.4% W09–W12 jump is a rebound from a W09 dip |
| pt43_edit_sort_and_annotate_target | yes | 3 | 0 | 18.9 | 18.9 | 1.943 | yes | pass | — | Dallas (91.2%) and Newark (92.6%) miss the 95.0% on-time SLA; the other six clear it |
| pt44_edit_replace_pie_with_delta | yes | 1 | 0 | 8.3 | 8.3 | 0.664 | yes | pass | — | Organic Search fell 9.4 pp while Paid Search gained 5.6 pp from Q1 to Q2 |
| pt45_edit_switch_to_cdf_tails | yes | 1 | 0 | 9.8 | 9.8 | 0.527 | yes | pass | — | checkout_v3 has a slow tail: p95 is 625 ms vs 185 ms for v2, despite similar means |
| pt46_surface_slide_exec_kpi | yes | 1 | 0 | 11.1 | 11.1 | 0.526 | yes | pass | — | Gross margin rose 11.4 pp in five quarters, to 68.2% |
| pt47_surface_dark_noc_monitor | yes | 1 | 0 | 8.4 | 8.4 | 0.534 | yes | pass | — | gru-sa-east TTFB runs about 119 ms, 3–5× every other PoP |
| pt48_repair_dual_axis_spaghetti | yes | 1 | 0 | 11.2 | 11.2 | 0.685 | yes | pass | — | Error rate peaked at 5.4% on Day 10, when CPU saturated at 84% |
| pt49_repair_pie_and_clipped_labels | yes | 1 | 0 | 6.9 | 6.9 | 0.571 | yes | pass | — | Timeouts are 31% of failures, not 42%; Timeouts and Auth Expired together cause over half |
| pt50_repair_unlabelled_log_scatter | yes | 1 | 0 | 11.4 | 11.4 | 0.622 | yes | pass | — | Parse time grows almost linearly with payload size (log–log slope 0.93, R² = 0.97) |
