<!-- mintfig:start -->
## Figures for people (`mintfig`)

- Before showing the user five or more numbers, send a figure instead: write the takeaway sentence first, then `fig = mint.explain(takeaway, mint.compare(...) | mint.trend(...) | mint.distribution(...) | mint.table(...) | ..., source=...)` and `summary = fig.save("out.png")`. Without Python, use `mintfig plot data.csv --kind auto --takeaway "..." --out out.png`.
- Name every interval (`error_label=`, `band_label=`), check the takeaway against `summary["panels"][i]["facts"]`, and send as soon as `summary["ship"]` is `true`, ignoring advisory warnings. Reply with `summary["deliver"]["markdown"]` (or `["text"]` in a code fence) plus the caption.
- For publication plates, run `mintfig run plot.py --journal nature --bundle out/ --json`, fix `severity == "error"` issues by their `fix_hint` for at most 2 rounds, and review clarity warnings such as `bar_baseline_nonzero`. Follow the Tufte rules: small multiples, direct labels, no rainbow colormaps, no `bbox_inches="tight"`.
- The full reference is the installed `mintfig` skill. If it isn't installed, run `mintfig skill --print` and read it down to "Publication Figures".
<!-- mintfig:end -->
