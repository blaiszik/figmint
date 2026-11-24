# Thread

**User:** Facilities sent daily meter readings for three campus buildings,
June to September: `data/daily_energy.csv`. The Library and the Lab annex got
the HVAC retrofit on 2026-07-16. The Gym didn't, so it's our comparison.

**Assistant:** Columns: `date` (ISO), `building`, `kwh` (daily electricity).
120 days per building. The Gym has a 4-day gap in early August (meter outage —
those `kwh` cells are empty). Weekends run about 30% lower than weekdays.

**User:** The sustainability office wants to know if the retrofit actually cut
consumption and by how much, before they fund the next three buildings.

**Assistant:** I'll compare each building before and after 16 July, using the
Gym to check that it wasn't just the season changing.

**User:** Great, one figure please — they read these on their phones.
