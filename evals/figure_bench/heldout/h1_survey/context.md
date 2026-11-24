# Thread

**User:** HR sent the results of the annual engagement survey:
`data/engagement_survey.csv`.

**Assistant:** Columns: `department` (7 departments), `response` (a five-point
scale from "very dissatisfied" to "very satisfied") and `count` (number of
people who gave that response). Department sizes differ, from about 40 to 160
respondents.

**User:** The leadership team wants to know which department is least
satisfied, and whether it's a clear outlier or just the bottom of a spread.
Count "satisfied" and "very satisfied" together as satisfied.

**Assistant:** I'll compare the share satisfied per department, accounting for
the different sizes.

**User:** One figure please, for the leadership channel.
