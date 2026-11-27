# Thread

**User:** Our 50-gene CRISPR synthetic-lethality screen is summarized in `data/crispr_lfc.csv` (4 sgRNAs
per gene).

**Assistant:** Columns: `gene`, `log2_fc`, `sd_lfc` (across 4 guides), `fdr`, and `n_guides`.

**User:** Make a rank-order figure highlighting all hits passing `FDR < 0.05` and calling out the
strongest synthetic-lethal dropout (`PRMT5`) with its guide-level spread.
