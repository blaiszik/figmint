# Thread

**User:** Interim Kaplan-Meier progression-free survival table from the phase 2
cohort is in `data/km_survival.csv` (120 patients per arm, 36-month follow-up).

**Assistant:** Columns: `arm` (`standard`, `combination`), `month` (0 to 36 in
2-month steps), `survival_prob`, `ci_low`, `ci_high` (Greenwood 95% CI), and
`n_at_risk`.

**User:** The tumor board wants to see both survival curves with their 95% CIs
and how much median survival shifts under the combination arm. Please make sure
the numbers at risk are clear too, because censoring accelerates after month 24.

**Assistant:** I'll plot the two Kaplan-Meier curves with 95% confidence bands,
mark the 50% median survival level, report the median survival gap, and show
how `n_at_risk` thins out late in follow-up.

**User:** Great, one figure for the clinical review chat.
