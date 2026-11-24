# figure-bench results: r2

- Passed: **9 / 10** (6 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 9 / 10
- Time to pass: median 22.4 s, total 263.8 s

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :--- | :--- |
| 01_ablation | yes | 1 | 0 | 17.5 | yes | — | The reranker buys 1.6 points of accuracy for 121 ms; the bigger encoder buys 0.5 points, within seed noise, for 60 ms |
| 02_ab_latency | yes | 1 | 0 | 19.8 | yes | — | The new flow cuts median checkout latency by 83 ms (424 → 341 ms), and the slow tail shrank too |
| 03_dose_response | yes | 1 | 0 | 19.7 | yes | — | CPD-7 is the one to take forward: it reaches 50% inhibition near 12 nM, about 12× more potent than CPD-2; CPD-4 never gets past 15% |
| 04_battery_fade | yes | 1 | 0 | 22.0 | yes | — | Baseline cells hit 80% end of life at ~460 cycles; FEC extends that to ~690 (+50%), VC to ~610 (+30%) |
| 05_retrofit | yes | 2 | 0 | 36.4 | yes | — | The retrofit cut daily electricity use 29% in the Lab annex and 18% in the Library; the un-retrofitted Gym fell only 3% |
| 06_energy_mix | yes | 1 | 0 | 22.4 | yes | — | Wind, solar and hydro supplied 34% of the region's electricity in 2025 |
| 07_gene_change | yes | 3 | 0 | 48.0 | yes | — | The drug switched on the p53 programme: all 6 p53 targets rose (median 2.5×), all 6 proliferation genes fell (median 0.55×), housekeeping stayed within 5% |
| 08_hall_petch | yes | 3 | 0 | 53.8 | yes | — | All three alloys are linear in 1/√d (r = 0.90–0.98); the Cu-Zn Hall–Petch slope is 327 MPa·√µm (R² = 0.94) |
| 09_eval_matrix | no | 3 | 0 | — | — | script_runs, one_figure_saved |  |
| 10_incident | yes | 1 | 0 | 24.2 | yes | — | Only payments spiked: on 13 Nov its error rate hit 2.1% of requests, about 270× its normal 0.008% |
