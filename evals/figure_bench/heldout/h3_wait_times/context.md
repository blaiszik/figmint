# Thread

**User:** Emergency department wait times from our two hospitals for October
are in `data/ed_waits.csv`.

**Assistant:** Columns: `hospital` (North, South), `triage_level` (1
resuscitation to 5 non-urgent) and `wait_min` (minutes from arrival to first
clinician contact), one row per patient. Waits are right-skewed.

**User:** The board thinks South is slower across the board. I suspect it's
only the less urgent patients. Which is it?

**Assistant:** I'll compare the two hospitals within each triage level.

**User:** One figure, please — it goes in the board pack.
