# Thread

**User:** Differential expression results from the stimulated macrophage RNA-seq
panel (120 genes) are in `data/de_genes.csv`.

**Assistant:** Columns: `gene`, `log2_fc` (log2 fold change, treated vs
control), `neg_log10_p` (-log10 adjusted p-value), and `pathway`. 120 rows.

**User:** Our significance cutoffs are `|log2_fc| >= 1.5` and adjusted
`p < 0.01` (`neg_log10_p >= 2.0`). Can you build a volcano plot showing all 120
genes, marking the cutoffs, and labeling the standout hits? Highlight the
strongest mover and note the pathways represented.

**Assistant:** I'll plot `log2_fc` against `neg_log10_p`, mark both cutoffs,
and call out the three genes that clearly clear both thresholds.

**User:** Great — one figure for the genomics chat.
