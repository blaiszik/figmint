---
name: mintfig
description: Use when showing a person five or more numbers (benchmarks, ablations, comparisons, trends, distributions, CSV/experiment outcomes, profiles, logs) so they get a message-first figure or table via mint.explain, mint.table, or `mintfig plot data.csv` with computed facts and a ship gate; before sharing any plain Matplotlib figure, script, or notebook (`mint.check`, `mintfig check plot.py`, `analysis.ipynb`); or for journal/manuscript plates (Nature, Science, Cell, PNAS, NeurIPS) needing exact mm geometry and preflight QA. Do NOT use for routine code edits, bug fixes, refactoring, unit tests, git operations, stack traces, architecture explanations, config/Docker changes, or replies with 1–3 scalar numbers (answer those in prose).
---

# mintfig: figures that say one thing

Install: `pip install mintfig`, `mintfig skill --install --global`, `mintfig mcp --install` (MCP + `ui://mintfig/figure` App), `mintfig hook --install`. Try `uvx mintfig demo`.

| Task | Read |
| :--- | :--- |
| Chat figure or table (most tasks) | This file down to "Publication Figures" |
| Intervals, replicates, log axes, units, small n, styles | `references/science.md` |
| Tidy rows, scorecards, `mint.edit`, `Session`, `brief`, HTML/terminal | `references/recipes.md` |
| Manuscript or journal plate | `references/publication.md` |

## Explain in a Conversation (`mint.explain`)

Plot for 5+ numbers or any comparison, trend, spread, or relationship; use `mint.table` for exact lookups, `mintchip` for inline prose chips or compact terminal/PR tables. Never plot 1–3 scalars or routine code tasks — reply in prose.

**1. Takeaway first.** One sentence with its number ("Removing retrieval costs 8 points of accuracy") becomes the title. One takeaway per figure.

**2. Pick each panel by question.** Every form accepts dicts, arrays, Series, or tidy rows (`list[dict]` / DataFrame).

| Question | Form | Wide or tidy input |
| :--- | :--- | :--- |
| Compare sizes | `mint.compare(values)` | `{name: num}`, `{cat: {s: num}}`, rows (`name=`, `value=`, `group=`) |
| Over order/time | `mint.trend(x, series)` | `(x, {s: [nums]})`, `("x", "s", y="y", data=rows)` |
| Before→after | `mint.change(before, after)` | two `{name: num}`, `("c1", "c2", data=rows, name="item")` |
| Spread of values | `mint.distribution(groups)` | `{g: [obs]}`, rows (`group=`, `value=`); `mint.histogram` for bins |
| Two measures | `mint.relate(x, y, x_label=, y_label=)` | two lists, `("x", "y", data=rows, names=, groups=)` |
| Part of whole | `mint.share(parts)` | `{name: num}`, rows |
| Two categories | `mint.matrix(values, rows=, cols=)` | 2-D array, wide DF, rows (`rows=`, `cols=`, `value=`) |
| Exact lookup | `mint.table(rows)` | `list[dict]`, DataFrame, `{col: [...]}`, 2-D + `columns=` |
| Bridge to total | `mint.waterfall(steps)` | `{step: delta}`, rows |
| Phase spans | `mint.timeline(spans)` | `{stage: (start, end)}`, rows |
| Pipeline attrition | `mint.flow(stages)` | `{stage: n}`, `[(stage, n, reason)]` |

**3. Name measures and highlights:** `label=`, `unit=`, `highlight=` (≤3; rest turn grey), `baseline=` (control, drawn in ink), `source=`. Name intervals (`error_label=`, `band_label=`). Unicode units (`µm`, `cm⁻³`, `°C`), never `$...$`.

```python
import mintfig as mint

fig = mint.explain(
    "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
    mint.compare({"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
               error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77),
                      "no fine-tuning": (0.66, 0.72)},
               error_label="95% CI, 5 seeds",
               title="Both losses are outside seed noise", label="Test accuracy",
               highlight=["no retrieval", "no fine-tuning"]),
    mint.trend([0, 500, 1000, 1500, 2000],
             {"full model": [0.02, 0.61, 0.76, 0.80, 0.82],
              "no retrieval": [0.02, 0.52, 0.67, 0.72, 0.74],
              "no fine-tuning": [0.01, 0.44, 0.60, 0.66, 0.69]},
             title="The gap opens in the first 500 steps", label="Validation accuracy",
             x_label="Training step"),
    source="runs/ablation_2026-11 (5 seeds per variant)",
)
summary = fig.save("ablation.png")          # dict; print() shows a compact JSON view
print(summary)
```

Zero-script CLI: `mintfig inspect data.csv` and `mintfig plot data.csv --kind auto --takeaway "..." --out fig.png`.

**4. Check summary, then ship.**
- Read `summary["panels"][i]["facts"]` (ranks, baseline gaps, CI overlap, `P(A > B)`, slopes); takeaway must match them.
- Ship when `summary["ship"]` is `true` (no errors, overlaps, clipping, or text < 11 px); ignore `low_density`. Else apply `fix_hint` (max 2 rounds).
- `ExplainError` names its rule/fix; `strict=False` or `with mint.lenient():` auto-adjusts soft limits (`summary["adjustments"]`).
- `print(summary)` is compact; `json.dumps(summary)` holds all keys (`narrative`, `alt_text`, `colors`, `display`).

**5. Deliver for the surface.** `summary["deliver"]` has `markdown`, `caption`, `text` (≤72 cols), and `html`.

| Surface | Render | Send |
| :--- | :--- | :--- |
| Image chat / sidebar | `width="chat"` (700 px) / `"narrow"` (450 px) | `deliver["markdown"]` |
| Artifact / inline HTML | `fig.save("fig.html", compact=True)` | single-SVG HTML (`themechange`); never hand-write SVG |
| Terminal (Ghostty/Kitty/SSH) | `fig.to_text(mode="braille", width="auto")` | 2×4 Braille + 24-bit ANSI (`NO_COLOR`-safe); `mode="ascii"` for 7-bit |
| PR / release KPI card | `mint.card(takeaway, metrics, panel=...)` | `.save_pair("pr")` or `.to_terminal()` |
| Notebook / Slide | return `fig` / `width="slide"` (1280 px) | inline / PNG |

Reply with takeaway, image, and caption — nothing more. Unsure of surface? Use `mintfig.surface.detect_surface()`, `fig.show()`, `mintfig doctor`, `mintfig mcp` (`ui://mintfig/figure`), or `mintfig demo`. One-flag terminal CLI (no `--out` needed): `mintfig plot|show|diff|watch ... --braille --style pine` and `mintfig card spec.json --terminal`.

### Already drawn with Matplotlib (`mint.check`)

Before sharing any Matplotlib figure, script, or notebook, run `mint.check(fig, "claim", dpi=...)` or `mintfig check plot.py|analysis.ipynb` (exit `0` ship, `1` fix, `2` error). Apply `fix_hint` until `ship` is `true`; `mintfig hook --install` automates this.

### Every argument (unknown args raise `ExplainError`)

```python
mint.explain(takeaway, *panels,
    kicker=None, subtitle=None, source=None, note=None,
    layout=None, colors=None, color_names=True, density="regular",
    style="mintfig",        # mintfig|mint|pine(mint_dark)|botanical|bold|editorial|paper|dark|mono|sketch
    palette=None,           # mint|spearmint|matcha|glacier|mineral|default|okabe_ito|tol|earth|ocean|berry
    accent=None, strict=True, width="chat")  # narrow|chat|slide

# Shared: title=, label=, unit=, highlight= (<=3), fmt= ; baseline= on compare/trend/distribution/table
mint.compare(values, name=None, group=None, value=None, sort=True, zero=True, log=False,
    error=None, inner_error=None, error_label=None, boost=None, boost_label=None,
    show_delta="auto", n=None, reference=None, facet=False, legend=False)
mint.trend(x, series=None, y=None, data=None, x_label=None, x_unit=None, log=False, log_x=False,
    zero=False, fit=False, band=None, band_label=None, points=None, points_label=None,
    events=None, regions=None, callouts=None, reference=None, end_values=True, facet=False, legend=False)
mint.change(before, after, data=None, name=None, labels=("Before", "After"))
mint.distribution(groups, group=None, value=None, stat="median",
    mode="dots", quantiles=20, bins=None, log=False, reference=None, facet=False)  # dots|swarm|quantile|ecdf
mint.histogram(values, group=None, value=None, bins="auto", stat="median", log=False, reference=None, facet=False)
mint.relate(x, y, x_label=, y_label=, data=None, x_unit=None, names=None, groups=None,
    fit=False, frontier=False, label_all=False, connect_groups=False,
    regions=None, callouts=None, log_x=False, log_y=False, reference=None, facet=False, legend=False)
mint.share(parts, name=None, value=None, top=7, kind="bars")  # bars|pie|donut (<=5)
mint.matrix(values, rows=None, cols=None, value=None, diverging=False, center=0.0,
    normalize=None, show_counts=False, triangle=None, mask_diagonal=False, highlight=None)
mint.forest(data, error=..., error_label=None, reference=0.0, pooled=None, n=None, log=False, sort=True)
mint.table(rows, columns=None, units=None, highlight=None, baseline=None, bold_best=False,
    sort=None, align=None, fmt=None, bars=None, interval=None, interval_label=None, spark=None)
mint.waterfall(steps, name=None, value=None, start=None, total_label="Total", show_total=True, reference=None)
mint.timeline(spans, name=None, start=None, end=None, group=None, x_label=None, sort=True, reference=None)
mint.flow(stages, name=None, value=None, reason=None, show_pct=True)
mint.custom(draw_fn, height_mm=48.0, describe="...")
```

### Limits

- **Strict** (`ExplainError`): `compare`/`timeline`/`table` ≤ 20, `change`/`waterfall` ≤ 14, `flow` ≤ 12, `distribution` ≤ 8 groups (≥ 3 obs), `matrix` ≤ 16×12, `table` ≤ 8 cols, `relate(groups=)` ≤ 4 (12 faceted), `trend` ≤ 4 series (12 faceted). Max 3 highlights, 4 colours, 6 panels; `too_tall` > 135 mm.
- `scales_differ`: merge into one `facet=` panel. Revise with `mint.edit("fig.png", ...)`, `mint.Session`, `mint.brief(...)` (`references/recipes.md`).

## Publication Figures

For manuscripts (`nature`, `science`, `science_advances`, `cell`, `pnas`, `neurips`, `screen`), read `references/publication.md` for journal specs, the script contract and Tufte primitives. In short:

1. Write `plot.py` exposing `def build(journal="nature") -> mint.Plate` (or a top-level `plate`/`fig`).
2. Run `mintfig run plot.py --journal nature --bundle out/ --json`.
3. Exit `0` means show `out/preview.png`. Exit `1` means fix each `severity == "error"` issue with its `fix_hint`, for at most 2 rounds. Exit `2` means fix the script contract or the exception.
4. Use the Tufte helpers `mint.pub.ghost_context`, `mint.pub.slopegraph`, `mint.pub.range_frame` and `mint.pub.direct_labels`. Never use rainbow/jet colormaps or `bbox_inches="tight"`.
