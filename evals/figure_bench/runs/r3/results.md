# figure-bench results: r3

- Passed: **10 / 10** (10 on the first submission); renders outside submit: 0
- Takeaway number matches the answer key: 10 / 10
- Time to pass: median 18.2 s, total 196.8 s

| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Failed checks | Takeaway |
| :--- | :---: | :---: | :---: | ---: | :---: | :--- | :--- |
| 01_ablation | yes | 1 | 0 | 17.9 | yes | — | The reranker buys 1.6 accuracy points for 121 ms; the bigger encoder's 0.5 points sit within seed noise |
| 02_ab_latency | yes | 1 | 0 | 14.8 | yes | — | The new flow cuts median checkout latency by 83 ms (424 → 341 ms), and the slow tail shrank too: p99 fell from 1,260 to 900 ms |
| 03_dose_response | yes | 1 | 0 | 17.1 | yes | — | Take CPD-7 forward: it hits 50% inhibition at about 12 nM, 13× lower than CPD-2; CPD-4 never passes 15% |
| 04_battery_fade | yes | 1 | 0 | 17.7 | yes | — | Baseline cells reach 80% retention near cycle 460; VC lasts about 150 cycles longer, FEC about 230 |
| 05_retrofit | yes | 1 | 0 | 22.3 | yes | — | The retrofit cut daily electricity 29% in the Lab annex and 18% in the Library; the un-retrofitted Gym fell only 3% |
| 06_energy_mix | yes | 1 | 0 | 20.9 | yes | — | Renewables supplied 34% of the region's electricity in 2025 |
| 07_gene_change | yes | 1 | 0 | 18.5 | yes | — | The drug switched on the p53 programme: p53 targets rose a median 2.5-fold, proliferation genes fell to 0.55×, housekeeping stayed flat |
| 08_hall_petch | yes | 1 | 0 | 22.7 | yes | — | All three alloys follow Hall–Petch (r ≥ 0.90); Cu-Zn's slope is 327 ± 57 MPa·µm½ (r = 0.97) |
| 09_eval_matrix | yes | 1 | 0 | 27.0 | yes | — | Swahili math rose 17 points but, at 45%, is still 22 points below any other language–task cell |
| 10_incident | yes | 1 | 0 | 17.9 | yes | — | Only payments spiked: on 13 Nov its error rate hit 2.1%, about 270× its usual 0.0077% |
