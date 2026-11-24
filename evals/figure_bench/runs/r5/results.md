# figure-bench results: r5

- Passed: **15 / 15** (15 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 15 / 15
- Time to pass: median 18.6 s, total 312.7 s
- Core tasks: {'tasks': 10, 'passed': 10, 'passed_first_try': 10, 'answers_correct': 10, 'median_seconds_to_pass': 18.8}
- Held-out tasks: {'tasks': 5, 'passed': 5, 'passed_first_try': 5, 'answers_correct': 5, 'median_seconds_to_pass': 17.7}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :--- | :--- |
| 01_ablation | yes | 1 | 0 | 18.5 | yes | — | The reranker buys 1.6 points for 121 ms; the bigger encoder buys 0.5 points, within seed noise, for 60 ms |
| 02_ab_latency | yes | 1 | 0 | 17.8 | yes | — | The new flow cuts median checkout latency by 83 ms (424 → 341 ms), and the slow tail shrank too |
| 03_dose_response | yes | 1 | 0 | 15.8 | yes | — | CPD-7 is the most potent: it reaches 50% inhibition near 12 nM, vs ~150 nM for CPD-2 and ~900 nM for CPD-9; CPD-4 never gets past 15% |
| 04_battery_fade | yes | 1 | 0 | 18.6 | yes | — | Baseline cells reach 80% end of life at about 460 cycles; FEC lasts ~230 cycles longer, VC ~150 |
| 05_retrofit | yes | 1 | 0 | 28.5 | yes | — | The retrofit cut daily electricity 29% in the Lab annex and 18% in the Library; the un-retrofitted Gym fell only 3% |
| 06_energy_mix | yes | 1 | 0 | 20.3 | yes | — | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | yes | 1 | 0 | 14.7 | yes | — | The drug switched on the p53 programme: all 6 p53 targets rose (median 2.5×) while proliferation genes fell to about half |
| 08_hall_petch | yes | 1 | 0 | 30.2 | yes | — | All three alloys follow Hall–Petch; the Cu-Zn slope is 327 MPa·µm½ (95% CI 270–385, r = 0.97) |
| 09_eval_matrix | yes | 1 | 0 | 26.0 | yes | — | Swahili gained most (+17 on math) but is still the weakest language; Swahili math, at 45%, trails every other cell by 22 points |
| 10_incident | yes | 1 | 0 | 18.9 | yes | — | Only payments spiked: 2.1% of requests failed on 13 Nov, about 278× its usual rate |
| h1_survey | yes | 1 | 0 | 17.7 | yes | — | Support is least satisfied (42%), but its interval overlaps Sales and Operations (54–55%): the bottom of a spread, not a clear outlier |
| h2_spectra | yes | 1 | 0 | 20.9 | yes | — | The 400 °C anneal red-shifts the absorption peak by 23 nm (520 → 543 nm); 200 °C moves it only 3 nm |
| h3_wait_times | yes | 1 | 0 | 31.9 | yes | — | South is slower only for less urgent patients: median waits match at levels 1–2 but run 10–45 min longer at levels 3–5 |
| h4_scaling | yes | 1 | 0 | 15.3 | yes | — | Mixture-of-experts scales best: loss falls as compute^-0.063, vs -0.050 for dense and -0.031 for recurrent |
| h5_budget | yes | 1 | 0 | 17.6 | yes | — | Yes: Libraries took the biggest cut (-18%), Parks lost 11%, and Housing grew 14% |
