# Thread

**User:** Cycling data for the electrolyte additive study is done:
`data/cycling.csv`. 1C/1C, 25 °C, graphite/NMC coin cells.

**Assistant:** Columns: `electrolyte` (baseline, additive FEC, additive VC),
`cell` (BL-1..4, FEC-1..4, VC-1..4), `cycle` (0–800 in steps of 50),
`retention_pct` (capacity retention, % of initial).

**User:** Our spec says end of life is 80% retention. I need to know roughly
when the baseline cells hit end of life, and how much longer the additives
last. Oh — VC-3 had a crimping defect, it falls off a cliff after cycle 200.
Leave it out of the comparison, but the figure has to say it was excluded.

**Assistant:** I'll plot retention against cycle number with the 80% line, show
the individual cells except VC-3, report where each electrolyte crosses 80%,
and note the exclusion on the figure.

**User:** Thanks — one figure for the group update.
