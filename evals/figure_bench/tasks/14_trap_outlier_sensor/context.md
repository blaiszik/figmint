# Thread

**User:** Continuous-flow reactor ramp log from yesterday's 36-hour campaign is
in `data/reactor_runs.csv`. We stepped the jacket setpoint up from ~180 °C to
~242 °C while sampling product yield every hour.

**Assistant:** Columns: `hour` (1–36), `temp_c` (reactor thermocouple, °C), and
`yield_pct` (% molar yield). 36 rows, no missing values.

**User:** Operations wants one figure for the shift handover note showing how
yield responds across the operating temperature range, plus the top operating
temperature and peak yield we achieved.

**Assistant:** Understood — plotting yield against reactor temperature and
summarizing the operating range and peak yield from `data/reactor_runs.csv`.

**User:** One figure please, going into the plant operations channel.
