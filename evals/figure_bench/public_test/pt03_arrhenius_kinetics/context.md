# Thread

**User:** Microreactor rate constants for our two supported catalysts (`Cat-Pt`
and `Cat-Ni`) from 500 K to 625 K in triplicate are in `data/kinetics.csv`.

**Assistant:** Columns: `catalyst`, `temp_k`, `inv_t_1000_k` (1000/T in K⁻¹),
`rate_const_s1` (s⁻¹), and `replicate` (1–3). 36 rows total.

**User:** We need an Arrhenius plot (`rate_const_s1` on a log y-axis vs
`1000/T`) showing all replicates and linear fits so we can compare activation
energies (in kJ/mol). Does `Cat-Pt` truly have a lower barrier than `Cat-Ni`,
and does `Cat-Ni` catch up at higher temperature?

**Assistant:** I'll plot both catalysts on a log-rate vs `1000/T` Arrhenius
scale, fit their slopes to report `Ea` in kJ/mol, and show the replicates.

**User:** Perfect — one figure for the catalysis group update.
