# Thread

**User:** Scaling runs for the three architecture families finished.
`data/loss_vs_compute.csv` has the final eval loss for each run.

**Assistant:** Columns: `family` (dense, mixture-of-experts, recurrent),
`train_flops` (1e18 to 1e22) and `eval_loss`. Nine compute budgets per family.

**User:** Which family scales best — i.e. whose loss falls fastest with
compute — and by how much? I need the exponent.

**Assistant:** On log–log axes a power law is a straight line, so I'll fit each
family's slope and compare.

**User:** One figure for the research sync.
