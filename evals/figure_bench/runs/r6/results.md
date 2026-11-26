# figure-bench results: r6 (mintfig arm)

- Passed: **14 / 15** (11 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 15 / 15
- Reply delivers the figure (<= 60 words of prose): 15 / 15 replies (0 not provided)
- Time to pass: median 16.6 s, total 248.3 s
- Core tasks: {'tasks': 10, 'passed': 9, 'passed_first_try': 7, 'answers_correct': 10, 'replies_deliver': 10, 'median_seconds_to_pass': 16.3}
- Held-out tasks: {'tasks': 5, 'passed': 5, 'passed_first_try': 4, 'answers_correct': 5, 'replies_deliver': 5, 'median_seconds_to_pass': 17.9}
- Neutral audit, first submission: {'saved': '14/15', 'clean': '14/15', 'text_legible': '14/14', 'no_text_overlap': '14/14', 'no_text_struck_by_lines': '14/14', 'text_well_formed': '14/14', 'no_text_clipped': '14/14', 'headline_has_number': '14/14', 'headline_correct': '13/14', 'reply_correct': '14/15', 'uncertainty_named': '3/3', 'median_min_text_px': 12.3, 'with_legend': 0}
- Neutral audit, final submission: {'saved': '15/15', 'clean': '15/15', 'text_legible': '15/15', 'no_text_overlap': '15/15', 'no_text_struck_by_lines': '15/15', 'text_well_formed': '15/15', 'no_text_clipped': '15/15', 'headline_has_number': '15/15', 'headline_correct': '15/15', 'reply_correct': '14/15', 'uncertainty_named': '4/4', 'median_min_text_px': 12.3, 'with_legend': 0}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | yes | 3 | 0 | 27.8 | yes | pass | — | The reranker adds 1.6 points for 121 ms of latency; the bigger encoder adds under 0.5, within noise |
| 02_ab_latency | yes | 1 | 0 | 16.3 | yes | pass | — | The new flow is 83 ms faster at the median (341 vs 424 ms), and its slow tail is shorter |
| 03_dose_response | yes | 1 | 0 | 17.5 | yes | pass | — | CPD-7 is the most potent (IC50 ≈ 12 nM); CPD-4 never passes 15% inhibition |
| 04_battery_fade | yes | 1 | 0 | 16.9 | yes | pass | — | Baseline cells reach 80% retention near cycle 460; FEC lasts about 230 cycles longer, VC about 150 |
| 05_retrofit | no | 3 | 0 | — | yes | pass | no_warnings | The retrofit cut weekday use 28% at the Lab annex and 17% at the Library; the Gym barely moved |
| 06_energy_mix | yes | 1 | 0 | 13.8 | yes | pass | — | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | yes | 2 | 0 | 25.0 | yes | pass | — | The drug switched on the p53 programme: targets up a median 2.5×, proliferation genes down 1.8×, housekeeping flat |
| 08_hall_petch | yes | 1 | 0 | 15.3 | yes | pass | — | All three alloys follow Hall–Petch; the Cu-Zn slope is 327 MPa·µm½ (R² 0.94) |
| 09_eval_matrix | yes | 1 | 0 | 12.7 | yes | pass | — | Swahili is still the weakest language, and Swahili math (45%) is the one bad cell |
| 10_incident | yes | 1 | 0 | 14.7 | yes | pass | — | Payments spiked to 2.1% on 13 Nov, about 280× its usual rate; no other service moved |
| h1_survey | yes | 1 | 0 | 17.9 | yes | pass | — | Support is least satisfied at 42%, well below the 54-72% of the other six, though Sales and Operations are close enough to overlap |
| h2_spectra | yes | 1 | 0 | 14.9 | yes | pass | — | The 400 °C anneal shifts the absorption peak by 25 nm, from 520 to 545 nm; 200 °C barely moves it |
| h3_wait_times | yes | 2 | 0 | 21.4 | yes | pass | — | South is slower only from triage level 3 down, by 10 to 45 minutes; levels 1 and 2 match North |
| h4_scaling | yes | 1 | 0 | 23.3 | yes | pass | — | Mixture-of-experts scales best: loss ∝ compute^−0.063, vs −0.050 dense and −0.031 recurrent |
| h5_budget | yes | 1 | 0 | 10.8 | yes | pass | — | Libraries took the biggest cut, -18%; Parks fell 11% and Housing grew 14% |
