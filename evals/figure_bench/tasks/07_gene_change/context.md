# Thread

**User:** RNA-seq quantification for the 24 h drug treatment is back. I pulled
24 genes of interest into `data/expression_tpm.csv`.

**Assistant:** Columns: `gene`, `condition` ("vehicle" or "drug 24h"),
`replicate` (1–3), `tpm`. You also sent `data/gene_groups.csv` mapping each
gene to a group: p53 target (6), proliferation (6), housekeeping (4) and other
(8).

**User:** I want to see whether the drug switched on the p53 programme. Which
groups moved, which way, and by how much? Housekeeping genes should stay flat
if the normalisation is OK. I care more about the groups than any single gene,
but name the biggest mover.

**Assistant:** I'll compare the replicate means per gene between vehicle and
drug as fold changes, organised so the groups can be read at a glance.

**User:** Thanks — one figure for lab meeting chat.
