# Thread

**User:** Tensile results for the grain-refinement series are in
`data/tensile.csv`: three alloy families, 12 specimens each, annealed to
different grain sizes.

**Assistant:** Columns: `alloy` (Al-Mg, Cu-Zn, Ni-Cr), `specimen`,
`grain_size_um` (mean linear-intercept grain size, µm; 2 to 80 µm),
`yield_mpa` (0.2% offset yield strength, MPa).

**User:** I need to check that all three follow Hall–Petch (yield strength
linear in d^-1/2), and I need the Hall–Petch slope for Cu-Zn for the report.

**Assistant:** I'll plot yield strength against d^-1/2 per alloy with a fit
each, and report the Cu-Zn slope and how well the line fits.

**User:** One figure please.
