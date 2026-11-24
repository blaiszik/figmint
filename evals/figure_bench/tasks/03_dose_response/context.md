# Thread

**User:** Plate reader data from the kinase panel is in
`data/inhibition.csv`. Four compounds, ten concentrations, triplicates.

**Assistant:** Columns: `compound` (CPD-7, CPD-2, CPD-9, CPD-4), `conc_nM` (0.1
to 3000 nM, half-log steps), `replicate` (1–3), `inhibition_pct` (% inhibition
relative to DMSO; values slightly below 0 or above 100 are assay noise).

**User:** The chemists want to know which compound to take forward. They care
about potency — roughly where each one hits 50% inhibition — and they'll want
to see the replicates, not just a fitted line. I think CPD-4 might be dead.

**Assistant:** I'll show the dose–response curves on a log concentration axis
with the 50% level marked, read off where each compound crosses it, and check
whether CPD-4 ever gets there.

**User:** Perfect. One figure please, it's going into the project chat.
