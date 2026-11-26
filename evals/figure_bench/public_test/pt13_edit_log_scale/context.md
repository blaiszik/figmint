# Thread

**User:** Pharmacokinetic time-course data for our four lead candidates is in
`data/pharmacokinetics.csv`, and your first plot is in `data/prior_figure.png`.

**Assistant:** Columns: `compound` (`CMP-A` to `CMP-D`), `hour` (0.5 to 24 h),
and `plasma_conc_ng_ml` (ng/mL, spanning roughly 2 to 2,400 ng/mL).

**User:** On the linear y-axis in `data/prior_figure.png`, everything after 8
hours is crushed flat against zero so you can't see which compound stays above
our `50 ng/mL` therapeutic floor at 24 hours. Can you switch the y-axis to a
log scale, highlight `CMP-C`, add the `50 ng/mL` reference line, and update the
headline with `CMP-C`'s 24-hour concentration?

**Assistant:** I'll regenerate the figure on a log concentration scale,
highlight `CMP-C`, mark the `50 ng/mL` floor, and state the 24-hour readout.

**User:** Perfect — one updated figure for the DMPK review chat.
