# Changelog

All notable changes to `mintfig` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once 1.0 is reached.

## [0.3.4] - 2026-11-28

### Added
- **Five promoted flagship surface themes (`style=`):** `prism` (aliases `npg`, `npg_clean`), `folio` (alias `npg_editorial`), `nordic`, `obsidian` (alias `pine_obsidian`), and `monograph` (alias `ivory`) — promoted to the top of `THEMES` and verified for grayscale separation (`>= 0.05`), deuteranopia/protanopia CVD distance (`>= 0.12`), and WCAG AA contrast (`>= 4.5:1`).
- **Intuitive `--matrix` CLI flag & `mode="matrix"` API alias:** Added `--matrix` across `explain`, `show`, `plot`, `diff`, and `watch`, plus `mode="matrix"` on `Explanation.to_text()`, `Explanation.show()`, and `show_in_terminal()` for 2×4 Unicode dot-matrix terminal charts while keeping `--braille` / `mode="braille"` as backwards-compatible aliases.
- **Flagship pure-white 3-panel hero, matching 116-column 3-panel dot-matrix counterpart, and Remotion showcase video/GIF (`gallery/make_repo_header.py`, `promo/demo-video/src/BrailleVideo.tsx`).**

### Changed
- **24-bit ANSI translucent CI ribbons in terminal dot-matrix plots (`terminal.py`):** Separated foreground, background, and band layers in `BrailleCanvas` so shaded 95% confidence bands render smoothly without corrupting line colors, with a non-colliding monochrome stipple fallback when `color=False`.
- **1:1 cross-surface color alignment (`terminal.py`):** Locked `baseline=` series in terminal `trend`, `ecdf`, `swarm`, and scorecard tables to neutral ink (`#E8F1EE` on dark themes) and added per-entity `row_colors` to terminal tables.
- **Cleaner booktabs `mint.table` styling (`_table.py`):** Removed noisy full-row colored background washes in favor of slim left accent stripes and contrast-safe entity-colored row labels.
- **ECDF guide-label fidelity (`_explain/distribution.py`):** Labeled horizontal `p50`/`p95` guides directly on the dashed lines, omitted crowded `p99` guides within 3% of `100%`, and replaced arbitrary-y right-margin labels with a compact `Curve (p95)` key.

## [Unreleased]

### Added
- **Wild Matplotlib & Seaborn artist extraction in `mint.check`:**
  - `QuadMesh` (`sns.heatmap`, `ax.pcolormesh`) value extraction, min/max/ratio facts, claim candidates, and colormap checks.
  - Colorbar axes exclusion so colorbars never trigger bogus `axis_unlabelled` errors or phantom panels.
  - Contiguous-edge histogram detection (`ax.hist`, `sns.histplot`) extracting bin count, total count, peak bin center/range, and median estimate.
  - `PolyCollection` envelope extraction (`ax.fill_between`, `sns.lineplot` CI bands) while preserving `interval_unlabelled` checks.
  - Boxplot and violinplot cluster detection (`ax.boxplot`, `sns.boxplot`, `ax.violinplot`) extracting per-group median/IQR/whisker facts without misreading geometry as data lines.
- **Cross-environment `uvx` / `--python` and Jupyter notebook checking:**
  - `mintfig check plot.py --python <path>` with automatic project `.venv` / `VIRTUAL_ENV` / `CONDA_PREFIX` detection so `uvx mintfig check plot.py` runs seamlessly against project-local packages (`pandas`, `seaborn`, `scipy`).
  - Zero-dependency `.ipynb` support via `mintfig check analysis.ipynb` and `check_notebook()`.
- **Wild-50 verification corpus (`evals/check_bench/`):** 50 deterministic Matplotlib/Seaborn test cases verifying `< 2%` false-positive rate and `> 90%` defect catch rate.
- **Global skill installation & full bundle printing:**
  - `mintfig skill --install --global` auto-detecting `~/.claude`, `~/.codex`, `~/.gemini`, and `~/.cursor`, plus `--target all` and `mintfig skill --print --all`.
- **Automatic agent `PostToolUse` hooks (`mintfig hook`):**
  - `mintfig hook --install`, `--uninstall`, `--status`, and `mintfig hook run` silently auditing agent-written Matplotlib scripts on write/edit/run and emitting `fix_hint` feedback only when `ship` is `false`.
- **Claude Code plugin package (`plugins/claude-code/`):** ready-to-install plugin bundle with synced `SKILL.md` + `references/`, `PostToolUse` hook config, and `/mintfig:check` command.
- **40-prompt skill trigger evaluation (`evals/trigger_eval/`):** 20 positive and 20 negative realistic prompts (none mentioning `mintfig`) with deterministic offline rubric scoring, `--live` CLI adapter (`claude`, `codex`, `gemini`), and pytest suite (`tests/test_trigger_eval.py`).
- **3-column README opener & comparison generator (`gallery/make_readme_comparison.py`):** side-by-side comparison of agent text-only, default agent Matplotlib (`ship: false`), and `mintfig` (`ship: true`) on identical ablation data, plus wedge-first adoption ordering (`mint.check` + `mintfig hook` alongside `mint.explain`).
- **Zero-rewrite Matplotlib upgrades (`src/mintfig/byo.py`, `gallery/byo_matplotlib_examples.py`):**
  - `mint.style(style="mintfig", *, palette=None, width="chat", accent=None)` leak-free context manager applying chat-readable sizing (>=11 px display text), CVD-safe palette cycles, despining, and `viridis` default cmap.
  - `mint.explain(takeaway, fig_or_ax, ...)` accepting plain Matplotlib/Seaborn `Figure`, `Axes`, or `SubFigure` objects directly as panels with `mint.check` facts, `ship` propagation, HTML, terminal, and `mint.brief` support.
  - Zero-dependency IPython/Jupyter magic (`%load_ext mintfig`, `%mintfig_check on|off|status`, `mint.byo.auto_check()`).
- **Opt-in legends & pie/donut charts (Workstream A):**
  - `mint.share(..., kind="bars" | "pie" | "donut")` (sorted bars remain default; pie/donut opt-in for <=5 parts with non-blocking `pie_close_slices` advisory when adjacent slices are within 5 pp).
  - Opt-in `legend=True` on `mint.trend`, `mint.relate`, and grouped `mint.compare` with frameless top legends (direct labels remain default).
- **SWE dev-tool ingestors, `mintfig diff`, and terminal/Markdown-first CLI (`src/mintfig/ingest.py`, `src/mintfig/diff.py`):**
  - Zero-dep parsers wired into `load_table_file`/`inspect_data`/`mintfig plot`: `hyperfine` JSON, `pytest-benchmark` JSON, `go test -bench` & `cargo bench` logs, GitHub Actions CI timings, Chrome Trace/OTEL spans, `k6` summaries, `esbuild`/`vite` metafiles, and LLM eval tables.
  - `mintfig diff base head` (`--out`, `--text`, `--markdown`, `--json`, `--fail-on-regression PCT`) with interval-overlap noise suppression (`within_noise`).
  - `--text` and `--markdown` stdout flags on `mintfig plot` (no PNG file needed).
- **GitHub PR cards, reusable GitHub Action, & 1.0 Stability Policy (`src/mintfig/pr_card.py`, `.github/actions/mintfig-check/`, `docs/STABILITY_POLICY.md`):**
  - `save_pr_card()` emitting light+dark PNGs with native GitHub `<picture>` markup and collapsible `<details>` facts/reproduce block, plus `format_check_pr_comment()`.
  - Reusable composite GitHub Action at `.github/actions/mintfig-check/action.yml` + manual example workflow.
  - SemVer & deprecation contract documented in `docs/STABILITY_POLICY.md`.

### Changed
- **False-positive hardening in `mint.check` / `epistemic.py`:** ignores non-metric model/precision tokens (`GPT-5`, `Llama-3.1`, `8B`, `FP16`, `INT4`, `v2.3`, `ResNet-50`), sample/design counts (`5 seeds`, `3 replicates`, `top-5`, `p < 0.05`, `95% CI`), and calendar years (`1990`–`2035`), while supporting common unit-scale conversions (`0.08` <-> `8%` <-> `8 points`, `0.08 s` <-> `80 ms`, `1500` <-> `1.5k`).
- **Sharpened `SKILL.md` and `AGENTS_SNIPPET.md` trigger criteria:** explicitly specifies both when to trigger (5+ numbers, comparisons/trends/distributions, plain Matplotlib/notebook checks, journal plates) and when NOT to trigger (routine code edits, refactors, bug fixes, tests, git, stack traces, config/Docker, 1–3 scalar numbers), while keeping the chat section under the 12 kB context budget.

## [0.3.0] - 2026-11-26

### Added
- **`mint.check(fig, claim)` and `mintfig check plot.py`:** audits any plain Matplotlib figure against its own plotted artist data and measures text legibility at reading width (`chat`, `narrow`, `slide`) with concrete `fix_hint`s and a `ship` gate.
- **Presentation & delivery layer:**
  - `summary["deliver"]` (`markdown`, `caption`, `text`, `html`), `fig.show()`, `fig.to_text()`, `fig.to_html()`, and `mintfig doctor`.
  - Entity-coloured names in titles (`color_names=True`), automatic delta brackets (`show_delta="auto"`), and `density="compact"`.
  - `mint.table` in-cell graphics (`bars=`, `interval=`, `spark=`).
  - `mint.brief(...)` multi-figure HTML and Markdown briefings with thumbnail overviews and collapsible data blocks.
  - `mint.Session` for consistent entity colours across multi-turn conversations and `mint.edit()` / `mint.load()` round-tripping from PNG-embedded specs.
  - Responsive HTML export (container queries for 360 px / 450 px / full width, light/dark mode, hover readouts, click-to-copy citations).
- **Progressive `SKILL.md`:** trimmed chat-figure core under 12 kB with modular `references/{science,recipes,publication}.md` files.
- **Plain-Matplotlib baseline in `evals/figure_bench/`:** `--arm matplotlib` and `--arm matplotlib-plain` with arm-neutral `savefig` auditing (`neutral.py`) and blind reader evaluation.

### Changed (Breaking)
- Streamlined top-level `mintfig` namespace to agent-facing entry points only (no legacy aliases; moved symbols raise an informative `AttributeError`):
  - Publication helpers → `mint.pub.*` (`mint.Plate` and `mint.figure` remain at top level).
  - Surface themes and palettes → `mint.themes`.
  - Audit utilities → `mint.audit`.
  - Skill installer helpers → `mint.skill`.
  - `explain_from_spec` → `mint.load`; `render_html`/`render_terminal`/`show_in_terminal` → `fig.to_html()`/`fig.to_text()`/`fig.show()`.
- Moved `pypdf` to optional extra `mintfig[pub]`.

## [0.2.1] - 2026-11-24

### Changed
- Renamed PyPI distribution and import package to `mintfig` (`import mintfig as mint`).
- Switched README gallery image links to absolute GitHub raw URLs for PyPI rendering.

## [0.2.0] - 2026-11-24

### Added
- **Message-first `mint.explain` API and 13 panel forms:** `compare`, `trend`, `change`, `distribution`, `histogram`, `relate`, `share`, `matrix`, `table`, `waterfall`, `timeline`, `flow`, and `custom` escape hatch.
- **Computed epistemic facts & audit-gated shipping (`summary["ship"]`):** rankings, gaps vs `baseline=`, interval overlap, `P(A > B)`, slopes, crossings, and lenient auto-adjustment mode (`strict=False`, `with mint.lenient():`).
- **7 surface themes & 6 CVD-tested palettes:** `mintfig`, `editorial`, `paper`, `bold`, `dark`, `mono`, `sketch`; `default`, `okabe_ito`, `tol`, `earth`, `ocean`, `berry`.
- **Zero-script CLI:** `mintfig inspect`, `mintfig plot`, `mintfig explain`, `mintfig edit`, `mintfig show`.
- **Publication plates & bundles (`mint.Plate`, `mintfig run --bundle`):** versioned specs for *Nature*, *Science*, *Science Advances*, *Cell*, PNAS, NeurIPS, and `screen`; 14-rule preflight QA; Tufte primitives (`direct_labels`, `range_frame`, `ghost_context`, `slopegraph`, `tufte_boxplot`, `sparkline`); CVD/grayscale proof sheets and reproducible bundles.
- **Bundled coding-agent skill installer:** `mintfig skill --install` supporting Claude Code, Antigravity, Cursor, Codex, `AGENTS.md`, and `CLAUDE.md`.
