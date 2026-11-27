<!-- mintfig:start -->
## Figures for people (`mintfig`)

- **When to use:** Before showing the user five or more numbers (benchmarks, ablations, comparisons, trends, distributions, CSV/experiment outcomes, profiles), send a figure instead: write the takeaway sentence first, then `fig = mint.explain(takeaway, mint.compare(...) | mint.trend(...) | mint.distribution(...) | mint.table(...) | ..., source=...)` and `summary = fig.save("out.png")`. Without Python, use `mintfig plot data.csv --kind auto --takeaway "..." --out out.png`.
- **When NOT to use:** Skip plotting for routine code edits, bug fixes, refactors, unit tests, git operations, stack traces, architecture explanations, config/Docker changes, or answers with 1–3 scalar numbers — reply directly in prose.
- **Inline chips vs. full figures:** Use `mintchip` for inline word-sized chips in prose or quick zero-dep terminal/PR tables; escalate to `mintfig` for full figures, multi-panel arguments, publication plates, and Matplotlib auditing.
- Name every interval (`error_label=`, `band_label=`), verify the takeaway against `summary["panels"][i]["facts"]`, and ship as soon as `summary["ship"]` is `true` (ignoring advisories). Reply with `summary["deliver"]["markdown"]` (or `["text"]` in a code fence) plus the caption.
- **Already drew plain Matplotlib?** Audit it before sharing with `mint.check(fig, takeaway)`, `mintfig check plot.py --python .venv/bin/python`, or `mintfig check analysis.ipynb`, and apply each `fix_hint` until `report["ship"]` is `true`. Run `mintfig hook --install` to enforce this automatically on agent plot writes.
- **Publication plates:** Run `mintfig run plot.py --journal nature --bundle out/ --json`, fix `severity == "error"` issues via `fix_hint` (max 2 rounds), review clarity warnings such as `bar_baseline_nonzero`, and follow Tufte rules (small multiples, direct labels, no rainbow colormaps, no `bbox_inches="tight"`).
- **Install / reference:** Install globally with `mintfig skill --install --global`. If not installed, run `mintfig skill --print` and read down to "Publication Figures".
<!-- mintfig:end -->
