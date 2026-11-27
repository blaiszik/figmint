# figure-bench results: v01_100_sonnet55_matplotlib_coached (matplotlib-coached arm)

- Passed: **56 / 100** (48 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 93 / 100
- Reply delivers the figure (<= 60 words of prose): 100 / 100 replies (0 not provided)
- Time to pass: median 12.9 s, mean 13.7 s, p90 19.2 s, total 765.5 s (first submit median 12.51 s, render median 0.604 s)
- Core tasks: {'tasks': 75, 'passed': 42, 'passed_first_try': 37, 'answers_correct': 69, 'replies_deliver': 75, 'median_seconds_to_pass': 12.9, 'median_seconds_total': 12.8, 'mean_seconds_to_pass': 13.6, 'p90_seconds_to_pass': 18.7}
- Held-out tasks: {'tasks': 25, 'passed': 14, 'passed_first_try': 11, 'answers_correct': 24, 'replies_deliver': 25, 'median_seconds_to_pass': 13.1, 'median_seconds_total': 14.1, 'mean_seconds_to_pass': 13.9, 'p90_seconds_to_pass': 19.8}
- Neutral audit, first submission: {'saved': '86/100', 'clean': '46/100', 'text_legible': '86/86', 'no_text_overlap': '71/86', 'no_text_struck_by_lines': '64/86', 'text_well_formed': '86/86', 'no_text_clipped': '76/86', 'headline_has_number': '86/86', 'headline_correct': '82/86', 'reply_correct': '67/100', 'uncertainty_named': '42/45', 'median_min_text_px': 14.6, 'with_legend': 2}
- Neutral audit, final submission: {'saved': '98/100', 'clean': '54/100', 'text_legible': '98/98', 'no_text_overlap': '81/98', 'no_text_struck_by_lines': '74/98', 'text_well_formed': '98/98', 'no_text_clipped': '86/98', 'headline_has_number': '98/98', 'headline_correct': '93/98', 'reply_correct': '68/100', 'uncertainty_named': '52/55', 'median_min_text_px': 14.6, 'with_legend': 2}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Total (s) | Render (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | ---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | yes | 2 | 0 | 27.2 | 27.2 | 1.244 | yes | pass | — | Reranker adds 1.6 pts; bigger encoder 0.5 pts |
| 02_ab_latency | yes | 1 | 0 | 23.3 | 23.3 | 1.141 | yes | pass | — | New flow median is 83 ms faster (95% CI -114 to -53);
no session in either arm reached 2 s |
| 03_dose_response | no | 1 | 0 | — | 12.8 | 0.697 | yes | pass | no_text_overlap | CPD-7 is most potent (IC50 ≈ 12 nM); CPD-4 peaks at 14% inhibition |
| 04_battery_fade | no | 1 | 0 | — | 16.5 | 0.734 | yes | pass | no_text_struck_by_lines | Baseline hits 80% at ~460 cycles; FEC adds ~230, VC ~150 |
| 05_retrofit | no | 1 | 0 | — | 27.5 | 10.891 | no | pass | no_text_clipped | Retrofit cut use 15–25 points more than the Gym's -2.9% drift |
| 06_energy_mix | yes | 1 | 0 | 17.3 | 17.3 | 0.965 | yes | pass | — | Renewables (wind, solar, hydro) supplied 33.7% of 2025 electricity |
| 07_gene_change | yes | 1 | 0 | 20.2 | 20.2 | 1.264 | yes | pass | — | Drug raises p53 targets 2.8× (log2 +1.48) and lowers
proliferation genes 0.53× (−0.91); housekeeping flat (−0.02) |
| 08_hall_petch | yes | 1 | 0 | 17.8 | 17.8 | 1.267 | yes | pass | — | All three alloys are linear in d$^{-1/2}$; Cu-Zn slope = 327 ± 57 MPa·µm$^{1/2}$ |
| 09_eval_matrix | yes | 1 | 0 | 19.8 | 19.8 | 0.912 | yes | pass | — | Swahili math is the one bad cell: 45.4% (+16.8 pts vs previous)
Swahili still trails every task by ~7+ pts; no cell regressed |
| 10_incident | no | 1 | 0 | — | 12.5 | 0.62 | yes | pass | no_text_overlap, no_text_struck_by_lines | Only payments spiked: 278× its median on Nov 13
other four services stayed within 1.5× of their median |
| 11_forest_meta | no | 1 | 0 | — | 10.8 | 0.547 | yes | pass | no_text_overlap | Pooled OR 0.75 (95% CI 0.67–0.84): clears 1.0;
COAST-3 and PLAINS-5 cross 1.0 alone (orange) |
| 12_survival_km | no | 1 | 0 | — | 14.2 | 0.898 | yes | pass | no_text_overlap | Combination extends median PFS by +6 months
(18 → 24 mo); bands = 95% CI (Greenwood) |
| 13_trap_overlapping_ci | no | 3 | 0 | — | 17.1 | 1.471 | yes | pass | no_text_struck_by_lines, no_text_clipped | cand_b is +0.60 F1 pts over baseline, within noise
(95% CIs overlap); not enough evidence to ship |
| 14_trap_outlier_sensor | no | 1 | 0 | — | 11.8 | 0.621 | yes | pass | no_text_struck_by_lines | Yield peaked at 84.7% at 240.9 °C, gains flatten above ~230 °C |
| 15_edit_switch_baseline | yes | 1 | 0 | 12.0 | 12.0 | 0.595 | yes | pass | — | cache_b serves +192 req/s (+31%) over control_v2 |
| 16_calibration_reliability | no | 1 | 0 | — | 10.9 | 0.619 | no | pass | no_text_overlap | Temperature scaling cuts ECE by 86% (0.118 → 0.017)
at identical AUROC 0.91 |
| 17_gpu_roofline_kernels | no | 1 | 0 | — | 11.8 | 0.805 | yes | pass | no_text_overlap, no_text_struck_by_lines | moe_grouped_gemm reaches only 49% of its roof (488 of 989 TFLOP/s);
other kernels reach 63–87% (labels: % of roof) |
| 18_db_query_plan_tail | no | 1 | 0 | — | 11.9 | 0.511 | yes | pass | no_text_overlap | Index cut orders_join p99 by 84% (150.5 → 24.6 ms);
order_insert p99 rose +57% (13.2 → 20.7 ms) |
| 19_trap_dual_axis_spurious | no | 1 | 0 | — | 15.3 | 0.744 | yes | pass | no_text_struck_by_lines | Solar and avocados correlate at r = 0.99, but only through shared growth |
| 20_trap_survivorship_bias | yes | 1 | 0 | 14.1 | 14.1 | 0.779 | yes | pass | — | Active accounts score 83.5, but the 24 that churned scored 36.3;
surveying only survivors overstates satisfaction |
| 21_edit_normalize_per_capita | yes | 1 | 0 | 11.7 | 11.7 | 0.583 | yes | pass | — | Cedar-Flats has the highest rate, 155 per 100k,
but its CI overlaps Pine-Ridge (139); both are ~3x Metro-North |
| 22_edit_split_confounder | yes | 1 | 0 | 12.4 | 12.4 | 0.571 | yes | pass | — | FP8 diverges from BF16 after ~45k steps:
+0.36 higher loss at 80k (3 runs each, thin = single runs, thick = mean) |
| 23_surface_narrow_oncall | no | 1 | 0 | — | 7.9 | 0.672 | yes | pass | no_text_struck_by_lines, no_text_clipped | checkout-api has 21.4% budget left,
below the 25% danger line |
| 24_surface_html_interactive_report | no | 1 | 0 | — | 11.7 | 0.507 | yes | pass | no_text_overlap | Android app F1 fell 9.4 pts since May (86.8 → 77.4);
other slices moved ≤1.1 pts, within CI noise |
| 25_repair_truncated_and_rainbow | yes | 1 | 0 | 9.9 | 9.9 | 0.524 | yes | pass | — | v1.3 beats v1.0 by +4.8 points (+6.0% relative)
80.2% → 85.0%; gap is far larger than seed SD (≤0.9) |
| h06_enzyme_michaelis | no | 1 | 0 | — | 15.0 | 0.739 | yes | pass | no_text_struck_by_lines, no_text_clipped | E142A raises Km 3.6× (5.8→21.1 µM) and lowers Vmax 7% (48.5→45.1 µM/min) |
| h07_cohort_attrition | no | 1 | 0 | — | 15.0 | 0.462 | yes | pass | no_text_clipped | 22.5% of patients (540 of 2,400) complete the 12-week endpoint;
largest drop at eligibility: −720 patients |
| h08_trap_overlap_clinical | yes | 1 | 0 | 10.1 | 10.1 | 0.491 | yes | pass | — | 150 mg vs 50 mg: -2.7 pg/mL, 95% CIs overlap
(no clear dose difference) |
| h09_trap_bad_batch | no | 1 | 0 | — | 16.0 | 0.457 | yes | pass | no_text_clipped | Treated reads 1.63× control (+0.26 OD) on the 4 valid plates |
| h10_edit_highlight_subset | no | 1 | 0 | — | 10.0 | 0.508 | yes | pass | no_text_struck_by_lines | TiN-3 (+2.8 pts) and BN-6 (+1.4 pts) exceed the 5.0% limit |
| h11_chrome_trace_build | no | 1 | 0 | — | 11.8 | 0.319 | yes | pass | no_text_overlap | lto_link is 43.7% of the 118.4 s build,
so extra codegen threads can't fix it |
| h12_hyperfine_within_noise | yes | 1 | 0 | 12.0 | 12.0 | 0.323 | yes | pass | — | Candidate is 7.4 ms faster (95% CI -17.9 to 3.1): within noise |
| h13_narrow_ide_sidebar | no | 1 | 0 | — | 14.9 | 0.436 | yes | pass | no_text_struck_by_lines | Median run time falls 59%: 188 s → 78 s |
| h14_repair_boxplot_claim | yes | 1 | 0 | 11.7 | 11.7 | 0.426 | yes | pass | — | ap-northeast median is 141.4 ms, 3.0× us-east (47.8 ms) |
| h15_repair_multipanel_ci | no | 1 | 0 | — | 14.5 | 0.532 | yes | pass | no_text_struck_by_lines | Cosine warmup beats baseline from epoch 6; +5.4 pts accuracy at epoch 25 |
| h16_pharmacokinetics_auc | no | 3 | 0 | — | 24.4 | 1.69 | yes | pass | no_text_overlap | Liposomal IV AUC₀₋₂₄ is 2.10× IR tablet
(Δ = +845 ng·h/mL, bootstrap 95% CI +705 to +995) |
| h17_catalyst_selectivity_tradeoff | yes | 1 | 0 | 9.9 | 9.9 | 0.567 | yes | pass | — | In2O3-ZrO2 gives the highest yield: 68.0% ± 1.8 (SD),
vs 55.4% ± 1.2 for Pd-Ga (n=4 runs each) |
| h18_gc_pause_tail_cdf | no | 1 | 0 | — | 11.9 | 0.545 | yes | pass | no_text_struck_by_lines, no_text_clipped | G1GC p99.9 pause is 142 ms: 11.3× ZGC (12.6 ms), 7.7× Go (18.4 ms) |
| h19_distributed_scaling_eff | yes | 1 | 0 | 12.9 | 12.9 | 0.464 | yes | pass | — | At 64 nodes NCCL keeps 81.2% efficiency vs 21.9% for Gloo-TCP
(59.3 points higher; run ranges do not overlap) |
| h1_survey | yes | 1 | 0 | 13.3 | 13.3 | 0.471 | yes | pass | — | Support is least satisfied (42%), but its range overlaps
Sales and Operations: lowest of a spread, not a clear outlier |
| h20_trap_ecological_fallacy | yes | 1 | 0 | 14.1 | 14.1 | 0.784 | yes | pass | — | Within every district, more tutoring goes with lower scores
(mean slope -3.0 pts/hr; district averages rise, r=+0.997) |
| h21_trap_missing_zero_truncation | yes | 1 | 0 | 14.3 | 14.3 | 0.588 | yes | pass | — | Charger-D is +1.7 points more efficient than Charger-A
(95.9% vs 94.2%) |
| h22_edit_add_control_and_exclude_drift | yes | 2 | 0 | 17.2 | 17.2 | 0.748 | yes | pass | — | Net lift = +6.0 a.u. (95% CI +4.9 to +7.1) |
| h23_surface_terminal_ci_diff | yes | 1 | 0 | 15.4 | 15.4 | 0.339 | — | pass | — |  |
| h24_surface_narrow_pr_comment | yes | 1 | 0 | 10.7 | 10.7 | 0.471 | yes | pass | — | type_check peak memory
-40% with arena (683→409 MB) |
| h25_repair_ci_and_wrong_p | yes | 2 | 0 | 20.9 | 20.9 | 0.796 | yes | pass | — | variant_x is +2.3 points (+3.5%) vs control,
but not significant (permutation p = 0.39) |
| h2_spectra | yes | 1 | 0 | 11.3 | 11.3 | 0.4 | yes | pass | — | 400 °C anneal red-shifts the peak by +25 nm (520→545);
200 °C: +5 nm, one grid step (5 nm) |
| h3_wait_times | yes | 2 | 0 | 21.1 | 21.1 | 1.107 | yes | pass | — | South's median wait is longer at triage 3–5 (+10 to +45 min),
not at 1–2 (within ±0.5 min). Bars: bootstrap 95% CI |
| h4_scaling | no | 1 | 0 | — | 16.5 | 0.441 | yes | pass | no_text_overlap | Mixture-of-experts scales best: loss exponent -0.063 vs dense -0.050 |
| h5_budget | no | 1 | 0 | — | 12.2 | 0.507 | yes | pass | no_text_overlap | Yes: Libraries took the biggest cut, -18.0%
Parks also fell; Housing grew most; the rest are roughly flat |
| pt01_volcano_omics | no | 1 | 0 | — | 14.1 | 0.476 | yes | pass | no_text_struck_by_lines | 3 of 120 genes pass both cutoffs; CXCL10 is strongest
(log2 FC +3.42, −log10 p 9.15) |
| pt02_raman_peaks | yes | 1 | 0 | 14.9 | 14.9 | 0.511 | yes | pass | — | 600 °C anneal shifts G band +16 cm⁻¹ (350 °C: +8); D band falls 39% |
| pt03_arrhenius_kinetics | yes | 2 | 0 | 18.3 | 18.3 | 1.117 | yes | pass | — | Cat-Pt's barrier is lower: 53 vs 85 kJ/mol (Δ = 32)
Cat-Ni gains with heat but Pt is still 3× faster at 625 K |
| pt04_rl_seed_curves | yes | 1 | 0 | 13.1 | 13.1 | 0.487 | yes | pass | — | SAC-tuned leads at 100k: +89 over TD3-clip, +134 over PPO-base;
worst SAC seed (816) beats best baseline seed (786) |
| pt05_alloy_replicates | yes | 1 | 0 | 10.3 | 10.3 | 0.469 | no | pass | — | T6-aged fails the 420 MPa spec: 2 of 8 coupons below it
(411.4, 416.8 MPa); all 8 T6 pass |
| pt06_ocean_ph_trend | no | 1 | 0 | — | 11.9 | 0.493 | yes | pass | no_text_struck_by_lines | Southern Ocean acidifies fastest: -0.026 pH/decade
(-0.051 over 20 yr; ±0.004 95% CI on slope) |
| pt07_trap_no_speedup | yes | 2 | 0 | 13.1 | 13.1 | 0.937 | no | pass | — | v2 is -2.8 ms vs v1 on average: not a clear speedup
(95% CI of diff -14.3 to +8.7 ms, n=10 each) |
| pt08_trap_simpson | yes | 1 | 0 | 13.6 | 13.6 | 0.554 | yes | pass | — | Treatment looks worse overall (58% vs 80%), but is better
within both severity groups (95% vs 90% mild, 52% vs 40% severe) |
| pt09_trap_small_n | no | 3 | 0 | — | 20.8 | 1.638 | yes | pass | no_text_clipped | Inhibitor mean is +27% vs vehicle, but not distinguishable
from noise (n = 3 per group) |
| pt10_trap_near_zero_pct | yes | 1 | 0 | 13.3 | 13.3 | 0.591 | yes | pass | — | Line-C rate rose 0.020% to 0.140% (+0.12 points, 7x);
other lines moved ≤0.004 points |
| pt11_trap_truncated_bait | yes | 1 | 0 | 11.0 | 11.0 | 0.489 | yes | pass | — | v4.2 raised overall success rate 97.4% → 98.6% (+1.2 pp)
All 4 regions up; point estimates, 300k–490k requests per cell |
| pt12_trap_missing_control | yes | 1 | 0 | 12.1 | 12.1 | 0.824 | no | pass | — | Treated fell -15.2% by week 8, but placebo fell -14.2%:
no clear treatment effect |
| pt13_edit_log_scale | no | 1 | 0 | — | 10.6 | 0.751 | yes | pass | no_text_struck_by_lines | Only CMP-C stays above the 50 ng/mL floor at 24 h (180.8 ng/mL) |
| pt14_edit_add_uncertainty | yes | 3 | 0 | 18.7 | 18.7 | 1.793 | yes | pass | — | High dose is +123 pg/mL over control
(95% CI 94 to 152) |
| pt15_edit_fix_units | yes | 2 | 0 | 13.9 | 13.9 | 1.266 | yes | pass | — | Board-D cuts load power to 1.49 W (-52% vs Board-A, -1.63 W) |
| pt16_hyperfine_diff | no | 1 | 0 | — | 10.0 | 0.515 | yes | pass | no_text_clipped | JSON parse is 30.8% faster on the branch; YAML is unchanged (-0.1%) |
| pt17_pytest_regression | no | 1 | 0 | — | 15.6 | 0.528 | yes | pass | no_text_clipped | search_query regressed +42.0% (18.7 → 26.5 ms); other 5 within ±3.8% |
| pt18_ci_pipeline_timeline | yes | 1 | 0 | 14.6 | 14.6 | 0.493 | yes | pass | — | integration-shard-3 blocks package-artifacts: 585 s,
325 s longer than the next-slowest shard (260 s) |
| pt19_k6_latency_deploy | yes | 1 | 0 | 13.0 | 13.0 | 0.715 | yes | pass | — | p99 rose 252 → 729 ms (+477 ms), above SLA all 30 min
after deploy; p50 barely moved (41.8 → 44.1 ms) |
| pt20_bundle_waterfall | no | 1 | 0 | — | 13.1 | 0.371 | yes | pass | no_text_clipped | Bundle grew +240.4 KB (+49.9%); date-locale-pack
alone adds +214.2 KB |
| pt21_llm_pareto_frontier | no | 1 | 0 | — | 12.5 | 0.724 | yes | pass | no_text_overlap | 3 of 10 configs are Pareto-optimal; 7 are strictly dominated |
| pt22_signup_funnel | yes | 1 | 0 | 11.3 | 11.3 | 0.599 | yes | pass | — | Email verify loses 46% of users (7,056) —
the biggest drop; only 23.5% reach first request |
| pt23_memory_soak_leak | no | 1 | 0 | — | 17.8 | 0.49 | yes | pass | no_text_struck_by_lines | worker-ingest leaks 18.0 MB/h (±0.2, 95% CI);
reaches 2,048 MB cap ≈ 42 h after the 48 h soak |
| pt24_narrow_phone_alert | yes | 1 | 0 | 15.0 | 15.0 | 0.764 | yes | pass | — | Isolated to eu-west: peaked at 14.3%,
rollback cut it below 1% by 18:33 |
| pt25_slide_quarterly_perf | yes | 1 | 0 | 13.0 | 13.0 | 0.722 | yes | pass | — | Asia-Pacific edge caching: p95 latency -106 ms (-35%), throughput +39% from Q2 to Q4 |
| pt26_dark_dashboard_card | yes | 1 | 0 | 9.7 | 9.7 | 0.506 | yes | pass | — | S3-FIFO leads hit rate: 89.4% vs 85.3% for TinyLFU (+4.1 pts)
Labels: hit rate · mean eviction CPU per op |
| pt27_terminal_only_bench | yes | 1 | 0 | 13.6 | 13.6 | 0.443 | — | pass | — |  |
| pt28_repair_ablation_bars | yes | 1 | 0 | 11.2 | 11.2 | 0.642 | yes | pass | — | Query rewrite adds 5.5 F1 points (full vs. without) |
| pt29_repair_jet_heatmap | yes | 1 | 0 | 10.4 | 10.4 | 0.641 | yes | pass | — | Accuracy is 73.2% (732/1000 tickets);
search tickets misrouted to infra: 46 (23% of search) |
| pt30_repair_line_struck | yes | 1 | 0 | 10.8 | 10.8 | 0.489 | yes | pass | — | v2.0 peaks at 4,820 req/s at c=64 (+47.9% over v1.0) |
| pt31_bland_altman | yes | 1 | 0 | 13.4 | 13.4 | 0.711 | yes | pass | — | Wearable reads +1.65 points high (95% limits -1.3 to +4.6, n=60);
error is larger when hypoxic: bias +2.2, SD 2.0 vs +1.2, SD 0.7 |
| pt32_xrd_phase_shift | no | 3 | 0 | — | 18.5 | 1.564 | yes | pass | no_text_overlap, no_text_struck_by_lines | 4% compressive strain shifts the (111) peak by Δ2θ = +0.69° ± 0.04°
(mean, 95% CI of n=3 scans; band = ±1 SD of scans) |
| pt33_crispr_screen_rank | yes | 1 | 0 | 12.5 | 12.5 | 0.476 | yes | pass | — | 4 of 50 genes pass FDR < 0.05; PRMT5 drops out most
(log2FC -3.45); bars = ±1 SD across guides |
| pt34_climate_ensemble_fan | no | 1 | 0 | — | 8.6 | 0.659 | yes | pass | no_text_overlap | By 2100, SSP3-7.0 median is +2.6 °C warmer than SSP1-2.6
Line = median, band = 10th–90th percentile of 12 models |
| pt35_cache_eviction_hitrate | no | 1 | 0 | — | 12.9 | 0.557 | yes | pass | no_text_overlap, no_text_struck_by_lines | S3-FIFO cuts miss ratio 7.1 pts vs LRU at 256 MB
(18.7% vs 25.8%) |
| pt36_token_throughput_batch | no | 1 | 0 | — | 11.5 | 0.577 | yes | pass | no_text_struck_by_lines | Batch 16 is the best within the 200 ms TTFT SLA:
747.7 tok/s at 168 ms |
| pt37_flaky_ci_heatmap | yes | 1 | 0 | 12.8 | 12.8 | 0.667 | yes | pass | — | Flakiness is concentrated in auth_oauth (22.6% by W06);
every other module stays at 2.4% or below |
| pt38_cloud_cost_waterfall | yes | 1 | 0 | 10.4 | 10.4 | 0.614 | yes | pass | — | Cloud bill rose a net +$41.2k (+32.2%); GPU Inference
added +$34.8k, 84% of the net increase |
| pt39_trap_multiple_testing | yes | 1 | 0 | 8.8 | 8.8 | 0.648 | yes | pass | — | search_click_depth +1.12% (raw p=0.038) does not survive
multiple-testing correction: BH-adj p=0.76; 0 of 20 significant |
| pt40_trap_heavy_tail_mean | yes | 1 | 0 | 12.8 | 12.8 | 0.666 | yes | pass | — | Mean is +48% ($52→$77) but median is −4% ($48→$46):
one $2,140 outlier drives the "win" (n=200 per arm, each dot an order) |
| pt41_trap_denominator_shift | yes | 1 | 0 | 9.3 | 9.3 | 0.515 | yes | pass | — | Alert rate fell 15.4% (13.0 to 11.0 per M requests), Jan to Jun |
| pt42_trap_cherry_picked_window | no | 1 | 0 | — | 12.9 | 0.609 | yes | pass | no_text_struck_by_lines, no_text_clipped | Signups are flat over 16 weeks (mean 99.8k); W09–W12's +18.4% is a rebound |
| pt43_edit_sort_and_annotate_target | no | 1 | 0 | — | 8.7 | 0.615 | yes | pass | no_text_struck_by_lines | 2 of 8 centers miss the 95.0% SLA: Dallas −3.8 pp, Newark −2.4 pp |
| pt44_edit_replace_pie_with_delta | no | 1 | 0 | — | 9.1 | 0.524 | yes | pass | no_text_overlap | Organic Search fell −9.4 pp while Paid Search rose +5.6 pp |
| pt45_edit_switch_to_cdf_tails | no | 1 | 0 | — | 14.7 | 0.611 | yes | pass | no_text_struck_by_lines | Same ~146 ms mean, but checkout_v3 p95 is 625 ms vs 185 ms (v2) |
| pt46_surface_slide_exec_kpi | yes | 1 | 0 | 11.1 | 11.1 | 0.694 | yes | pass | — | Gross margin up +11.4 pp in 5 quarters, to 68.2% |
| pt47_surface_dark_noc_monitor | no | 1 | 0 | — | 13.4 | 0.562 | yes | pass | no_text_struck_by_lines | gru-sa-east is the outlier: median TTFB 120.8 ms,
2.9x the next-slowest PoP (42.0 ms) |
| pt48_repair_dual_axis_spaghetti | no | 1 | 0 | — | 10.1 | 0.61 | yes | pass | no_text_struck_by_lines | Day-10 error rate peaked at 5.4% as CPU hit 84% |
| pt49_repair_pie_and_clipped_labels | yes | 1 | 0 | 7.6 | 7.6 | 0.53 | yes | pass | — | Timeouts are 31.4% of failures (314 of 1,000), not 42% |
| pt50_repair_unlabelled_log_scatter | yes | 1 | 0 | 11.3 | 11.3 | 0.882 | yes | pass | — | Parse time scales ~linearly: slope 0.93, R² = 0.97 |
