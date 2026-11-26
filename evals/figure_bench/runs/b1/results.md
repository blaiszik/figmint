# figure-bench results: b1 (matplotlib arm)

- Passed: **15 / 15** (12 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 4 / 15
- Reply delivers the figure (<= 60 words of prose): 15 / 15 replies (0 not provided)
- Time to pass: median 19.5 s, total 319.3 s
- Core tasks: {'tasks': 10, 'passed': 10, 'passed_first_try': 7, 'answers_correct': 3, 'replies_deliver': 10, 'median_seconds_to_pass': 21.6}
- Held-out tasks: {'tasks': 5, 'passed': 5, 'passed_first_try': 5, 'answers_correct': 1, 'replies_deliver': 5, 'median_seconds_to_pass': 18.3}
- Neutral audit, first submission: {'saved': '15/15', 'clean': '12/15', 'text_legible': '15/15', 'no_text_overlap': '14/15', 'no_text_struck_by_lines': '15/15', 'text_well_formed': '15/15', 'no_text_clipped': '13/15', 'headline_has_number': '9/15', 'headline_correct': '4/15', 'reply_correct': '15/15', 'uncertainty_named': '3/4', 'median_min_text_px': 15.3, 'with_legend': 6}
- Neutral audit, final submission: {'saved': '15/15', 'clean': '15/15', 'text_legible': '15/15', 'no_text_overlap': '15/15', 'no_text_struck_by_lines': '15/15', 'text_well_formed': '15/15', 'no_text_clipped': '15/15', 'headline_has_number': '9/15', 'headline_correct': '4/15', 'reply_correct': '15/15', 'uncertainty_named': '3/4', 'median_min_text_px': 15.3, 'with_legend': 6}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | yes | 2 | 0 | 27.1 | yes | pass | — | Reranker: worth ~1.6 pts. Encoder: ~0.5, near noise |
| 02_ab_latency | yes | 1 | 0 | 19.5 | no | pass | — | New flow is faster at the median and in the tail |
| 03_dose_response | yes | 1 | 0 | 18.8 | no | pass | — |  |
| 04_battery_fade | yes | 1 | 0 | 19.3 | no | pass | — | Thin lines: individual cells; thick lines: mean. Dots: where the mean crosses 80%.
VC-3 excluded from the comparison (crimping defect). |
| 05_retrofit | yes | 1 | 0 | 16.1 | no | pass | — | Weekday electricity, after vs before 16 July |
| 06_energy_mix | yes | 1 | 0 | 27.6 | yes | pass | — | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | yes | 2 | 0 | 30.2 | no | pass | — | p53 targets up, proliferation down, housekeeping flat |
| 08_hall_petch | yes | 1 | 0 | 16.4 | no | pass | — |  |
| 09_eval_matrix | yes | 2 | 0 | 23.7 | yes | pass | — | Swahili improved most, but Swahili math (45%) is the one weak cell |
| 10_incident | yes | 1 | 0 | 23.8 | no | pass | — | Only payments spiked; the other four stayed flat |
| h1_survey | yes | 1 | 0 | 18.3 | no | pass | — | Support is lowest, but not a clear outlier:
Sales and Operations overlap with it |
| h2_spectra | yes | 1 | 0 | 22.6 | yes | pass | — | 400 °C anneal red-shifts the peak by about 22 nm |
| h3_wait_times | yes | 1 | 0 | 25.6 | no | pass | — | South is slower from level 3 down, not at levels 1-2 |
| h4_scaling | yes | 1 | 0 | 16.9 | no | pass | — | Mixture-of-experts loss falls fastest with compute |
| h5_budget | yes | 1 | 0 | 13.4 | no | pass | — | Budget change, FY2025 to FY2026 (%) |
