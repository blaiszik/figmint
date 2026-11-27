# Thread

**User:** Thermal-cycling resistance drift results for our seven dielectric
coatings (1,000 cycles, 6 coupons each) are in `data/thermal_cycling.csv`, and
your earlier chart is in `data/prior_figure.png`.

**Assistant:** Columns: `material` (seven coatings), `delta_r_pct` (mean %
resistance drift), `sd_pct` (±1 SD), and `n_coupons` (6 each).

**User:** Qualification fails if drift exceeds `5.0%`. On
`data/prior_figure.png`, all seven coatings look equally emphasized and the
`5.0%` limit isn't drawn, so reviewers have to hunt for the failures. Can you
update the figure to highlight ONLY the two failing materials (`TiN-3` and
`BN-6`), keep the five passing coatings muted, add the `5.0%` spec reference
line, and focus the takeaway on the two failures?

**Assistant:** I'll update the figure to highlight `TiN-3` and `BN-6`, add the
`5.0%` spec line, keep the ±1 SD error bars, and state how far the two failures
exceed the limit.

**User:** Perfect — one revised figure for the reliability review.
