# Thread

**User:** Observational recovery data from our regional clinic registry (540
patients) is in `data/clinical_outcomes.csv`.

**Assistant:** Columns: `patient_id`, `severity` (`mild`, `severe`), `arm`
(`control`, `treatment`), and `recovered` (`1` = recovered at day 14, `0` = not
recovered). 540 rows.

**User:** Someone in morning standup computed the overall recovery rate and
claimed `treatment` is doing much worse than `control` (~58% vs 80%) and wants
to pause it immediately. Can you analyze `data/clinical_outcomes.csv` and make
one figure showing what is actually happening?

**Assistant:** Understood — analyzing recovery outcomes across the full table
in `data/clinical_outcomes.csv`.

**User:** Thanks — one clear figure for the clinical governance chat.
