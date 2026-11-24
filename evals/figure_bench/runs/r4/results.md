# figure-bench results: r4

- Passed: **15 / 15** (14 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 15 / 15
- Time to pass: median 20.0 s, total 311.0 s
- Core tasks: {'tasks': 10, 'passed': 10, 'passed_first_try': 10, 'answers_correct': 10, 'median_seconds_to_pass': 19.8}
- Held-out tasks: {'tasks': 5, 'passed': 5, 'passed_first_try': 4, 'answers_correct': 5, 'median_seconds_to_pass': 24.2}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :--- | :--- |
| 01_ablation | yes | 1 | 0 | 18.6 | yes | — | The reranker adds 1.6 points for 121 ms; the bigger encoder's 0.5 points is within seed noise, for 60 ms |
| 02_ab_latency | yes | 1 | 0 | 16.7 | yes | — | The new flow cuts median checkout latency by 83 ms (424 → 341 ms), and the slow tail shrank too |
| 03_dose_response | yes | 1 | 0 | 14.6 | yes | — | CPD-7 is the most potent, reaching 50% inhibition near 12 nM; CPD-4 never gets past 15% |
| 04_battery_fade | yes | 1 | 0 | 29.3 | yes | — | Baseline cells reach 80% end of life at ~460 cycles; FEC lasts ~230 cycles longer, VC ~150 |
| 05_retrofit | yes | 1 | 0 | 19.6 | yes | — | The retrofit cut daily electricity use 29% at the Lab annex and 18% at the Library; the Gym fell only 3% |
| 06_energy_mix | yes | 1 | 0 | 21.8 | yes | — | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | yes | 1 | 0 | 19.3 | yes | — | The drug switched on p53: its targets rose a median 2.5× (top: CDKN1A, 7.0×) and proliferation genes fell to 0.55× |
| 08_hall_petch | yes | 1 | 0 | 23.3 | yes | — | All three alloys follow Hall–Petch (r ≥ 0.90); Cu-Zn's slope is 327 MPa·µm½ (95% CI 270–385) |
| 09_eval_matrix | yes | 1 | 0 | 21.1 | yes | — | Swahili math rose 17 points to 45% but is still the weakest cell, 22 points below any other; Swahili's other tasks gained about 5 |
| 10_incident | yes | 1 | 0 | 20.0 | yes | — | Only payments spiked: on 13 Nov its error rate hit 2.1%, about 270× its usual 0.0077% |
| h1_survey | yes | 1 | 0 | 25.7 | yes | — | Support is least satisfied at 42%, but it is the bottom of a spread, not a clear outlier |
| h2_spectra | yes | 1 | 0 | 19.6 | yes | — | The 400 °C anneal red-shifts the absorption peak by 21 nm (520 → 541 nm); 200 °C moves it only 3 nm |
| h3_wait_times | yes | 1 | 0 | 25.3 | yes | — | South is slower only for less urgent patients: median waits 17–46% longer at triage 3–5, level with North at 1–2 |
| h4_scaling | yes | 2 | 0 | 24.2 | yes | — | Mixture-of-experts scales best: loss falls as compute^-0.063, vs -0.050 for dense and -0.031 for recurrent |
| h5_budget | yes | 1 | 0 | 11.9 | yes | — | Libraries took the biggest cut (−18%), Parks lost 11% and Housing grew 14%; the other nine moved less than 5% |
