# Thread

**User:** We validated a wearable pulse oximeter against arterial blood gas SaO2 across 60 clinical
readings (`data/spo2_agreement.csv`).

**Assistant:** Columns: `patient_id`, `arterial_sao2_pct`, `wearable_spo2_pct`, `pair_mean_pct`, and
`diff_wearable_minus_ref_pct`.

**User:** Make a Bland–Altman agreement figure showing the mean bias and 95% limits of agreement
(±1.96 SD), and call out whether error worsens in the hypoxic range (< 90% SaO2).
