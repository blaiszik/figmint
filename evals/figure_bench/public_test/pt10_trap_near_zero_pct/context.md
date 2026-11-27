# Thread

**User:** Inspection counts across our four assembly lines before and after the
solvent vendor change (50,000 units per line per period) are in
`data/wafer_defects.csv`.

**Assistant:** Columns: `line` (`Line-A` to `Line-D`), `period` (`before`,
`after`), `inspected_units` (50,000 each), `defects`, and `defect_rate_pct`.

**User:** An alert email just went out saying "Line-C defects exploded by +600%"
and people are talking about halting production. Can you build one clear figure
for the plant ops channel showing what actually happened across all four lines?

**Assistant:** Understood — examining before/after defect counts and rates for
all four lines in `data/wafer_defects.csv`.

**User:** One figure please, so everyone can see the real magnitude at a glance.
