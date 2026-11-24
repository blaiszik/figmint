<!-- figmint:start -->
## Scientific Figures (`figmint`)

- To explain a result to the user in a conversation, write the takeaway sentence first, then call `fm.explain(takeaway, fm.compare(...) | fm.trend(...) | fm.change(...) | fm.distribution(...) | fm.histogram(...) | fm.relate(...) | fm.share(...) | fm.matrix(...), source=...)` and `print(fig.save("out.png"))` (or `figmint explain spec.json --out out.png`). Show uncertainty and name it (`error=` with `error_label=`, `band=` with `band_label=`, raw observations via `fm.distribution`, `fm.histogram`, or `trend(points=)`), use `log=`/`log_x=` for values spanning decades, check the takeaway against `facts`, and send right away once `summary["ship"]` is `true` (do not re-render for minor advisory warnings). For fast ad-hoc chat charts where soft limits should auto-adjust instead of raising, use `with fm.lenient():` / `strict=False` / `--lenient`. For chat figures read `SKILL.md` only down to "Publication Figures".
- Build publication figures with `figmint.Plate` or `figmint.figure`, exposing `def build() -> Plate | Figure` (or top-level `plate` / `fig`) plus optional `CAPTION` / `TAKEAWAY` / `PANEL_NOTES`.
- Validate and export every figure with: `figmint run plot.py --journal nature --bundle out/ --json` (supports `nature`, `science`, `science_advances`, `cell`, `pnas`, `neurips`, `screen`).
- Repair `severity == "error"` items using `issues[].fix_hint`, `panels`, and `element_locations`; review clarity warnings (`color_separation`, `clarity_metadata`, `bar_baseline_nonzero`, `chartjunk_hints`, `text_on_data`).
- Enforce a **2-loop repair cap** (`<= 2` fixes), then inspect and show `out/preview.png` to the user.
- Apply Tufte discipline: favor small multiples (`fm.ghost_context`), `fm.slopegraph`, `fm.sparkline`, `fm.range_frame`, and `fm.direct_labels` over boxed legends or spaghetti plots; reserve saturated ink for focal findings and keep bar baselines at zero.
- Use perceptual colormaps (`viridis`, `magma`, `cividis`, `figmint_navy`, `figmint_div`), never `jet`/`rainbow`, and never use `bbox_inches="tight"`.
<!-- figmint:end -->
