# figure-bench results: r1

- Passed: **10 / 10** (10 on the first submission)
- Takeaway number matches the answer key: 10 / 10
- Time to pass: median 32.5 s, total 361.7 s

| Task | Pass | Attempts | Time to pass (s) | Answer | Failed checks | Takeaway |
| :--- | :---: | :---: | ---: | :---: | :--- | :--- |
| 01_ablation | yes | 1 | 22.9 | yes | — | Dropping the reranker costs 1.6 points of accuracy; the smaller encoder costs 0.5, within seed noise |
| 02_ab_latency | yes | 1 | 33.8 | yes | — | The new flow is faster for a typical user (median 424 → 341 ms) and its slow tail shrank too; no session in either arm took 2 s |
| 03_dose_response | yes | 1 | 35.4 | yes | — | CPD-7 is the most potent: 50% inhibition at about 12 nM, 13× below CPD-2 (~150 nM) and 77× below CPD-9 (~890 nM) |
| 04_battery_fade | yes | 1 | 29.3 | yes | — | Baseline cells reach 80% end of life at ~460 cycles; FEC lasts ~230 cycles longer (~690) and VC ~160 longer (~620) |
| 05_retrofit | yes | 1 | 53.1 | yes | — | The HVAC retrofit cut daily electricity use by 28% in the Lab annex and 17% in the Library; the un-retrofitted Gym fell only 2% |
| 06_energy_mix | yes | 1 | 31.2 | yes | — | Wind, solar and hydro supplied 34% of 2025 generation (177 of 526 TWh); contested biomass is another 1.8% |
| 07_gene_change | yes | 1 | 28.7 | yes | — | The drug switched on the p53 programme: its four targets rose 1.9–5.8-fold (CDKN1A 5.8×), proliferation genes fell to 0.39–0.62×, housekeeping genes stayed within 10% |
| 08_hall_petch | yes | 1 | 55.2 | yes | — | All three alloys follow Hall–Petch (r = 0.90–0.98); Cu-Zn slope k = 327 MPa·µm½ (95% CI 270–385) |
| 09_eval_matrix | yes | 1 | 41.6 | yes | — | It is mainly a language problem (Swahili averages 61% vs English 85%), plus one bad combination: Swahili math at 45% |
| 10_incident | yes | 1 | 30.5 | yes | — | Only payments spiked: on 13 Nov 2.1% of its requests failed, about 271× its usual rate |
