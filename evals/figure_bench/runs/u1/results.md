# figure-bench results: u1 (matplotlib-plain arm)

- Passed: **2 / 15** (2 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 4 / 15
- Reply delivers the figure (<= 60 words of prose): 15 / 15 replies (0 not provided)
- Time to pass: median 14.8 s, total 29.6 s
- Core tasks: {'tasks': 10, 'passed': 1, 'passed_first_try': 1, 'answers_correct': 3, 'replies_deliver': 10, 'median_seconds_to_pass': 15.2}
- Held-out tasks: {'tasks': 5, 'passed': 1, 'passed_first_try': 1, 'answers_correct': 1, 'replies_deliver': 5, 'median_seconds_to_pass': 14.4}
- Neutral audit, first submission: {'saved': '14/15', 'clean': '2/15', 'text_legible': '6/14', 'no_text_overlap': '12/14', 'no_text_struck_by_lines': '7/14', 'text_well_formed': '12/14', 'no_text_clipped': '13/14', 'headline_has_number': '6/14', 'headline_correct': '4/14', 'reply_correct': '14/15', 'uncertainty_named': '2/3', 'median_min_text_px': 10.9, 'with_legend': 7}
- Neutral audit, final submission: {'saved': '15/15', 'clean': '2/15', 'text_legible': '6/15', 'no_text_overlap': '13/15', 'no_text_struck_by_lines': '7/15', 'text_well_formed': '12/15', 'no_text_clipped': '14/15', 'headline_has_number': '7/15', 'headline_correct': '4/15', 'reply_correct': '14/15', 'uncertainty_named': '3/4', 'median_min_text_px': 10.9, 'with_legend': 7}

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Delivery | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :---: | :--- | :--- |
| 01_ablation | no | 1 | 0 | — | no | pass | no_text_overlap, no_text_struck_by_lines, no_text_clipped | What each component buys |
| 02_ab_latency | no | 1 | 0 | — | no | pass | no_text_struck_by_lines | New flow is faster across the whole distribution; no session reaches 2 s |
| 03_dose_response | no | 1 | 0 | — | no | pass | text_legible |  |
| 04_battery_fade | no | 1 | 0 | — | yes | pass | text_legible, no_text_struck_by_lines | VC-3 excluded (crimping defect, fails after cycle 200). 1C/1C, 25 °C, graphite/NMC coin cells. |
| 05_retrofit | no | 1 | 0 | — | no | pass | no_text_struck_by_lines, text_well_formed | Daily use, smoothed |
| 06_energy_mix | no | 1 | 0 | — | yes | pass | text_legible | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | no | 2 | 0 | — | no | pass | text_legible, no_text_struck_by_lines, text_well_formed | p53 targets up, proliferation genes down, housekeeping flat |
| 08_hall_petch | yes | 1 | 0 | 15.2 | no | pass | — |  |
| 09_eval_matrix | no | 1 | 0 | — | yes | pass | text_legible | Swahili gained 5 to 17 points but is still the weakest language; Swahili math (45%) is the one outlier |
| 10_incident | no | 1 | 0 | — | no | pass | text_legible, no_text_struck_by_lines | Only payments spiked; the other four stayed flat |
| h1_survey | no | 1 | 0 | — | no | pass | text_legible, no_text_struck_by_lines | Support is the least satisfied department, well below the rest |
| h2_spectra | no | 1 | 0 | — | no | pass | no_text_overlap, no_text_struck_by_lines |  |
| h3_wait_times | no | 1 | 0 | — | no | pass | text_legible | South is slower only for triage levels 3-5; levels 1-2 are the same |
| h4_scaling | yes | 1 | 0 | 14.4 | no | pass | — | Mixture-of-experts has the steepest scaling exponent |
| h5_budget | no | 1 | 0 | — | yes | pass | text_legible, text_well_formed | Libraries took the deepest cut (-18%); Housing grew most (+14%) |
