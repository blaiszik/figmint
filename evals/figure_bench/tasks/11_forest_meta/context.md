# Thread

**User:** We finished extracting the six randomized trials of extended
prophylaxis vs standard care for post-op thromboembolism. Summary odds ratios
and inverse-variance pooled estimate are in `data/meta_trials.csv`.

**Assistant:** Columns: `trial` (six trials plus `Pooled (IV)`), `year`,
`n_patients` (total 2,440), `odds_ratio`, `ci_low`, `ci_high` (95% CI), and
`weight_pct`. Values below 1.0 favor extended prophylaxis.

**User:** The guideline committee wants one forest-style summary figure showing
each trial's odds ratio and 95% CI alongside the pooled estimate. They want to
know the pooled effect size, whether it clears the null line of 1.0, and which
smaller trials still cross 1.0 on their own.

**Assistant:** I'll plot each trial's odds ratio with its 95% CI relative to
the 1.0 null reference line and highlight the pooled estimate.

**User:** Perfect — one clean figure for the committee chat.
