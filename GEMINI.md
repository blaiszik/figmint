# mintfig — Visual Briefing & Figure QA Instructions

Use `mintfig` whenever a user needs to inspect five or more numbers (benchmarks, ablations, trends, distributions, CSV/experiment outputs, profiles, or logs), audit an existing Matplotlib figure, or build a publication-ready journal plate.

## Escalation Rules

- **1–3 scalar numbers or routine coding tasks** (edits, bug fixes, tests, git, stack traces, configs) → reply in prose. Do **not** plot.
- **Inline word-sized sparklines, intervals, or compact terminal/PR tables** → use `mintchip` (or the `mint_chip` MCP tool).
- **5+ numbers, comparisons, trends, distributions, multi-panel arguments, Matplotlib audits, interactive HTML/MCP App views, or journal plates** → use `mintfig`.

## MCP Tools (`uvx mintfig mcp`)

This extension wires the `mintfig` MCP server automatically. Prefer these tools when working directly from data, specs, or existing plot files — they return a verified PNG, a 72-column terminal Braille summary, computed `facts`, a `ship` verdict, and an interactive `ui://mintfig/figure` MCP App view:

- **`mint_explain`** — Render a message-first 1–4 panel figure from a JSON spec (`takeaway`, `panels`, optional `kicker`, `subtitle`, `source`, `style`, `palette`, `width`).
- **`mint_check`** — Audit any existing Matplotlib `.py` script or `.ipynb` notebook against its plotted data and reading-width legibility (`path`, optional `claim`, `width`). Apply `fix_hint` until `ship` is `true` (max 2 rounds).
- **`mint_plot_file`** — Auto-infer and render a figure straight from CSV, TSV, JSON, hyperfine, pytest-benchmark, or JUnit files (`path`, optional `takeaway`, `kind`, `style`, `palette`).
- **`mint_card`** — Build a PR or release KPI summary card with bold tiles, deltas, inline sparklines, and an optional companion panel (`takeaway`, `metrics`, optional `panel`, `style`).
- **`mint_chip`** — Render an inline `mintchip` micro-graphic or shared-scale terminal/Markdown table when `mintchip` is installed.

## CLI & Python Workflows

Drop to the CLI or Python when transforming large DataFrames/NumPy arrays, iterating inside a terminal, or building manuscript plates:

- **Terminal & zero-script CLI:**
  - `mintfig plot data.csv --braille --style pine` — 2×4 Unicode Braille + 24-bit ANSI chart directly in the terminal.
  - `mintfig check plot.py --claim "..."` — audit an existing Matplotlib script or `.ipynb` notebook (exit `0` ship, `1` fix, `2` error).
  - `mintfig demo` — 15-second terminal showcase (`--html showcase.html` for all 6 surfaces).
  - `mintfig doctor` — report detected harness/surface, graphics protocol, `mintchip`, and MCP config status.
- **Python API:**
  - Use `mint.explain(takeaway, *panels)`, `mint.table(rows)`, `mint.card(...)`, and `mint.check(fig, "claim")`.
  - Use `mintfig.surface.detect_surface()` when choosing delivery formats programmatically, or `fig.save("fig.html", compact=True)` for lean inline Antigravity HTML embeds (never hand-write SVG).
  - For journal plates (`nature`, `science`, `cell`, `pnas`, `neurips`), build a `mint.Plate(...)` and validate with `mintfig run plot.py --journal nature --bundle out/ --json`.

## Non-Negotiable Quality Rules

1. **Takeaway first:** State the conclusion and its key number in the headline; verify every stated number against computed `facts`.
2. **Name uncertainty:** Always pass `error_label=` / `band_label=` when drawing intervals or bands.
3. **Respect the ship gate:** Only deliver figures with `ship: true` (no overlaps, clipped text, truncated bar baselines, or text under 11 px at reading width).
