---
description: Audit a Matplotlib/Seaborn plotting script, Jupyter notebook, or journal PDF figure with mintfig check
argument-hint: <plot.py | analysis.ipynb | figure.pdf> [--claim "..."] [--width chat|narrow|slide] [--journal nature]
allowed-tools: Bash(mintfig check:*), Bash(uvx mintfig check:*), Read, Edit
---

Run `mintfig check` on the target in `$ARGUMENTS` (if `mintfig` is not on `PATH`, fall back to `uvx mintfig check`):

```bash
mintfig check $ARGUMENTS
```

Review the check report:
- If every figure reports `SHIP` (exit code 0), report that the figure passed and mention any brief advisories.
- If any figure reports `FIX FIRST` (exit code 1), summarize each blocking issue and its `fix_hint`, apply the minimal fix to the plotting script, and re-run `mintfig check` until every figure passes.
- For a publication PDF (for example `figure.pdf --journal nature`), verify column width, embedded vector fonts (zero Type 3 fonts), and image DPI compliance.
