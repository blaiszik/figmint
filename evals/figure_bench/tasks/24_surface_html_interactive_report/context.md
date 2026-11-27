# Thread

**User:** We're embedding a 6-month ML monitoring chart into our internal HTML engineering report
(700 px article column). Data is in `data/model_drift_monthly.csv`.

**Assistant:** Columns: `month` (2026-05..2026-10), `slice` (`us_web`, `eu_web`, `ios_app`, `android_app`),
`f1_pct`, `ci95_half_pct` (95% CI half-width), and `n_eval` (2,000/month/slice).

**User:** Show which traffic slice is drifting and by how many points since May, with 95% CI bands so
reviewers can tell real degradation from eval noise.
