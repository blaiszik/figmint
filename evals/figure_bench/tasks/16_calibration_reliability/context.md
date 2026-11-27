# Thread

**User:** We evaluated temperature scaling on our fraud classifier (`data/calibration_bins.csv`).
Both models have the exact same AUROC (0.91), so accuracy alone won't show why calibration matters.

**Assistant:** Columns: `model` (`uncalibrated_resnet`, `temp_scaled`), `mean_pred_prob` (10 decile bins),
`n_samples`, `n_positive`, `empirical_freq`, and `ci95_half` (binomial 95% CI half-width).

**User:** Can you plot a reliability diagram comparing both models against the perfect-calibration diagonal
and quantify how much temperature scaling cuts Expected Calibration Error (ECE)?
