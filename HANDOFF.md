# figmint — handoff

Written 2026-11-24 at the end of the review-and-fix pass, updated after a
second pass on agent usability (section 4b), a third pass with figure-bench
(section 4c), and a fourth pass reviewing the benchmark work, adding a full
GitHub gallery and fixing newly discovered agent rough edges (section 4d).
Self-contained: you do not need the previous conversations.

## 1. What this project is for

`figmint` is a Matplotlib toolkit, a CLI and an agent skill.

- **Primary goal (the owner's words):** make this an indispensable tool to
  improve communication between agent and human for complex scientific work:
  figures that carry dense information a person could not take in as text,
  single or multi panel, grounded in rules that best convey information.
- **Secondary goal:** beautiful and reproducible publication figures.

| Path | Entry point | For |
| :--- | :--- | :--- |
| Conversation | `fm.explain(...)` / `figmint explain spec.json` | An agent answering a person. |
| Publication | script contract + `figmint run --bundle` | Journal plates (`nature`, `science`, `cell`, `pnas`, `neurips`, ...). |

## 2. Current state

- Repository: `https://github.com/blaiszik/figmint`, branch `main`, MIT. The
  owner asked for all three passes to be committed and pushed; ask before committing
  or pushing in a later pass unless told.
- Package `figmint` 0.2.0, Python >= 3.10, `uv`-managed `.venv`.
- **The name `figmint` is taken on PyPI.** The owner will choose a distribution
  name; nothing is renamed yet. Free on 2026-11-24 (checked against the PyPI
  JSON API): `mintfig`, `plotmint`, `figsay`, `figtell`, `figwise`, `figproof`,
  `figbrief`, `clearfig`, `plainfig`, `tellfig`, `sayplot`, `figclaim`,
  `figstory`, `pyfigmint`, `figmint-py`. The import name can stay `figmint`
  whatever the distribution is called.
- Tests and lint: see section 5 for the numbers at the end of this pass.

```bash
MPLCONFIGDIR=/tmp/mpl-figmint .venv/bin/pytest -q
.venv/bin/ruff check src tests gallery evals
MPLCONFIGDIR=/tmp/mpl-figmint .venv/bin/python gallery/explain_science_examples.py
MPLCONFIGDIR=/tmp/mpl-figmint .venv/bin/python gallery/explain_chat_examples.py
MPLCONFIGDIR=/tmp/mpl-figmint .venv/bin/python gallery/explain_style_showcase.py
MPLCONFIGDIR=/tmp/mpl-figmint .venv/bin/figmint explain --example
```

Shell is zsh: unquoted `$var` is not word-split. A formatter runs on save (ruff
format), so files are longer than they read. Default-style `fm.explain` runs
print nothing to stderr (the `findfont` noise came from the mathtext `cal` slot
and is fixed in `themes.py`); `post.stringData` font-tool noise elsewhere is
harmless.

### How the owner works (observed, respect these)

- Commands that delete or overwrite existing output were declined twice in an
  earlier pass. Do not delete files or overwrite `evals/output/` or the older
  plates under `gallery/output/` without asking. In this pass the three
  `gallery/output/explain*` folders were regenerated because the code that
  draws them changed; the previous renders are kept locally in `.archive/`
  (git-ignored).
- The owner has twice asked for the main model to review and for fixes to be
  delegated to Opus subagents.
- Style, palette and example names must be neutral. The owner had the styles
  renamed from publication names to `bold`, `editorial`, `sketch` "to avoid
  issues". Do not reintroduce a publication, company or product name as an
  identifier, alias, comment or output path.
- The owner works across agents (Claude, Gemini) and passes handoffs between
  them. Keep this file current when you finish.

## 3. `fm.explain` in one page

```python
import figmint as fm

fig = fm.explain(
    "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",  # the takeaway is the title
    fm.compare({...}, error={...}, error_label="95% CI, 5 seeds",
               title="Both losses are outside seed noise", label="Test accuracy",
               highlight=["no retrieval", "no fine-tuning"]),
    fm.trend(steps, {...}, title="The gap opens in the first 500 steps",
             label="Validation accuracy", x_label="Training step"),
    source="runs/ablation_2026-11 (5 seeds per variant)",
)
summary = fig.save("ablation.png")   # a dict (prints as JSON): panels[i]["facts"], issues, alt_text, colors
```

`baseline="name"` on `compare`, `trend` and `distribution` marks a control or
"before" state: it is drawn in ink (never a highlight colour) and every item's
facts are stated against it, absolute and relative.

Seven forms, each chosen by the question the panel answers: `compare` (size),
`trend` (change over order), `change` (two states), `distribution` (spread),
`relate` (two measures), `share` (part of whole), `matrix` (two categorical
dimensions), plus `custom(draw_fn)` as an escape hatch. The complete argument
reference lives in `src/figmint/assets/SKILL.md`, and
`tests/test_skill_doc.py` fails if a public argument is missing from it or its
example stops running clean.

Rules applied by construction (sources are tabulated in `README.md`):

- The title is the takeaway sentence; each panel has a lettered headline.
- Bars are sorted and start at zero; `zero=False`, `error=` or `log=True`
  switch to dots. No pies, no dual axes, no legends, no rotated text.
- At most 4 coloured series and 3 highlights; otherwise grey context or
  `facet=True`. Violations raise `ExplainError(message, fix_hint, rule)`.
- **A name keeps one colour across every panel of a figure** (figure-level
  registry built in `explain()`); `colors={name: "blue"|"red"|"green"|"amber"}`
  pins it across figures, and the summary's `colors` key reports the result.
- Uncertainty must be named: `error_label=` / `band_label=`, else the warning
  `interval_unlabelled`. Raw replicates via `distribution` or
  `trend(points=)`.
- Numbers keep their magnitude: about 3 significant figures, `1.3×10⁻⁷` for
  very small or large values, never rounded to zero, no signed zero.
- Layout is computed from content: 140 mm wide, exported 1400 px for a ~700 px
  chat column; smallest text 12.3 px at display size.
- `summary["panels"][i]["facts"]` are computed from the data (highest, lowest,
  ratios from unrounded values, differences from the highlighted item or the
  baseline, whether intervals overlap, crossings and which series stay above a
  reference, before/after medians at `events=`, log slopes split at an
  interior peak, whether distribution ranges separate, far values, missing
  values) so the agent can check its takeaway. x values carry the unit given
  at the end of `x_label` ("Time (h)" -> "19 h").
- Every plausible wrong call raises `ExplainError` with the fix, including
  unknown arguments (the hint lists the valid ones and the nearest name).
- Every PNG embeds its spec (`figmint:spec` text chunk); `fm.load(path)` and
  `figmint explain fig.png --out new.png` rebuild the figure from it.

### Files

| File | What |
| :--- | :--- |
| `src/figmint/explainer.py` | Forms, number formatting, facts, colour registry, layout engine, `Explanation`, `Summary`, spec entry points, PNG embedding, `load`. One large module (see section 6). |
| `src/figmint/themes.py` | Frozen `Theme` dataclass and the four styles: `figmint`, `bold`, `editorial`, `sketch`. |
| `src/figmint/cli.py` | `figmint explain <spec.json, fig.png or -> --out fig.png [--style] [--write-spec] [--show-spec] [--example]`. Exit 0 rendered, 1 rendered with an error-level issue, 2 spec rejected. |
| `src/figmint/assets/SKILL.md`, `AGENTS_SNIPPET.md` | What an agent reads. The conversation path leads; the publication workflow follows. |
| `tests/test_explain*.py`, `tests/test_skill_doc.py` | Forms and rules, data handling and facts, visual behaviour (colours, symbols, collisions), styles, and the doc-drift guard. |
| `gallery/explain_science_examples.py` | Five scientific reference figures (synthetic data) -> `gallery/output/explain_science/`. |
| `gallery/explain_chat_examples.py`, `gallery/explain_style_showcase.py` | Six general figures -> `gallery/output/explain/`, and the same six in the three extra styles -> `gallery/output/explain_styles/`. |

### How the layout works (you will touch this)

`explain()` builds a `matplotlib.figure.Figure` directly with an Agg canvas (no
pyplot, no global rcParams; everything runs inside the theme's rc context). It
wraps header and footer text by measuring it, asks each panel for a natural
plot height, sums the rows to get the figure height, then for each panel
creates an axes and calls `_fit_axes`, which resizes the axes until its tight
bounding box exactly fills the panel's cell. "Finishers" run afterwards: label
de-collision, tick thinning from measured label widths (`_fit_ticks`), event
and reference label placement, facet width equalisation, matrix header and
cell checks. Fonts resolve at draw time, so drawing and saving must happen
inside the same rc context. Runs of super- or subscripts are drawn as mathtext
in the body font; `µ` is mapped to the upright Greek mu; glyphs no font can
draw are reported as `glyph_missing`.

## 4. What this pass did

1. **Review by rendering.** Eleven scientific scenarios and forty edge cases
   were rendered and inspected, and three blind tests were run: fresh agents
   given only `SKILL.md`, a dataset and a scientist's question (ML ablation,
   doped-film transport, dose-response). The blind tests were the most useful
   input; their findings drove most of the fixes.
2. **What was wrong.** Values such as 1.3e-7 printed as "0" and 3.2e15 as
   "3,200,000B"; pandas inputs were rejected; `±` errors and several band
   shapes crashed with raw exceptions; the skill never mentioned log axes,
   `fmt`, `band`, matrix highlights or where `note=` goes, so agents guessed
   keyword names; the same name changed colour between panels; x tick labels,
   event labels, matrix headers and reference labels collided without any
   issue being raised; `µ` rendered slanted and `ℏ` as a box; facts gave
   meaningless percentages and ignored intervals.
3. **Fixes (done by Opus subagents from written briefs, verified here).**
   Number formatting, input handling, error messages, facts, new arguments
   (`sort="asc"`, `log` on compare, `log_x`, `points`, `band_label`,
   `error_label`, `end_values`, `stat="mean"`, `groups`, flexible matrix
   `highlight`, `colors`), the figure-level colour registry, symbol rendering,
   collision handling, PNG spec embedding and `fm.load`.
4. **Renamed the styles** to `bold`, `editorial`, `sketch` (no aliases to the
   old names; two font names that carried a brand were dropped from the sketch
   font stack).
5. **Docs.** `SKILL.md` conversation section rewritten with a complete
   argument reference and a section on scientific data; README leads with the
   conversation path; a scientific gallery added.
6. **Release hygiene.** `pyproject.toml` metadata and a trimmed sdist (it was
   28 MB because it bundled gallery output), `.gitignore` for local folders,
   first commit on top of the remote's initial commit.

One change touched the publication path: `preflight._visible_texts` used an
absolute tick tolerance of 1e-12, which counted off-screen log tick labels as
visible on axes with tiny data and raised a false `canvas_clipping` error. It
is now a relative tolerance. The publication tests pass; the 2-loop repair
eval was not re-run.

## 4b. Second pass: agent usability (commit `4d301e6`)

Method: build figures from `SKILL.md` alone and time them, then two more blind
tests on random data (a cell-biology knockdown study; an LLM-serving ops review
with a config change). Neither blind agent hit an exception. Their friction was
that `facts` could not check the claims they made, so they computed numbers in
pandas; distribution facts also ran to 30 lines. Fixed (the main session found
and verified; the large batch was done by an Opus subagent from a written
brief):

1. `baseline=` on `compare`, `trend`, `distribution` (new public argument,
   documented, carried through the spec, misuse raises with a hint).
2. `trend`: before/after medians per series at each `events=` marker; repeated
   crossings summarised ("cross 12 times; a is above b from 15 Oct on");
   series that never cross a reference say which side they stay on; the first
   coloured series is compared with every other coloured one.
3. Log-axis slopes are fitted on each side of an interior peak or trough, not
   across it (an absorption phase hid the elimination rate); fold changes use
   one wording per panel ("falls 186-fold, 2.3 decades").
4. x unit parsed from the end of `x_label` (`_x_unit`) and used in every fact
   that names an x value, and in slopes ("per h").
5. `distribution`: pairs limited to the baseline or the highlighted groups;
   range separation robust to one outlier ("all but 1 of 8 ..."); far values
   flagged (4 × 1.4826·MAD); range and a ratio in each line.
6. `change` facts give percentages and one line for the items that barely
   moved; `share` gives the highlighted parts' combined share; `matrix` skips a
   constant diagonal and reports highlighted cells.
7. Date ticks carry their month ("15 Sep, 1 Oct"); two `_fit_ticks` loops on
   narrow facet panels fixed; the `reference_label_collides` hint no longer
   suggests a full-width row (that triggered `too_tall`), and the label tries
   spots along the line before giving up.
8. `SKILL.md`: what `save()` returns (a dict), DataFrame orientation per form,
   highlight colour order, `baseline=`, a before/after-event recipe, x units in
   `x_label`, and that first→last facts are endpoint values.

Timed one-shot figures after the fixes: about 10 s from a blank script to a
clean render (`ok: true`, no issues) for a two-panel figure on fresh random
data, with no re-render.

## 4c. Third pass: figure-bench and three fix cycles

`evals/figure_bench/` (see its README) is a benchmark of how fast an agent turns a
conversation plus data into a clean chat figure. Each task is a mock agent
thread (`context.md`) and seeded data; a fresh agent sees only its task folder
and `SKILL.md`. `bench.py start|submit|grade|recheck` times it from `start` to
the first passing `submit` (max 3). Checks: figmint's own (`ok`, **no
warnings**, text >= 11 px at 700 px, chat width, a number in the takeaway,
titled panels, no `fm.custom`, embedded spec, source, alt text) plus an
**independent layout audit** that rebuilds the figure from its spec and inspects
every drawn text (no overlaps, no text crossed by a line, no "%%", repeated
words, ASCII minus or "nan"). `grade` also scores the takeaway's number against
a hidden key (`answers.json`; agents are told not to read it). Ten core tasks
(`tasks/`) and five **held-out** tasks (`heldout/`, added after cycle 1 and never
used to tune anything). `make_data.py` regenerates everything deterministically.

Results (fresh agents each run; `runs/*/results.md`; `progress.png` is drawn by
`make_progress.py` with figmint):

| Run | What changed before it | Passed | First try | Resubmissions | Mean / median time |
| :--- | :--- | :---: | :---: | :---: | :---: |
| r1 | first, easy task set (not comparable) | 10/10 | 10 | 0 | — / 32.5 s |
| r2 | tasks and checks hardened | 9/10 | 6 | 7 | 30.4 / 22.4 s |
| r3 | cycle 1 | 10/10 | 10 | 0 | 19.7 / 18.2 s |
| r4 | cycle 2 (+5 held-out) | 15/15 | 14 | 1 | core 20.4 / 19.8, held-out 21.3 / 24.2 s |
| r5 | cycle 3 | 15/15 | 15 | 0 | core 20.9 / 18.8, held-out 20.7 / 17.7 s |

Every graded takeaway matched its answer key from r3 on. Most of the gain came in
cycle 1; the core tasks then plateaued at about 20 s, which is mostly the agent
reading SKILL.md and the data.

What the cycles changed (Opus subagents from written briefs, verified here;
tests 467 → 515):

- Cycle 1: `fmt`+`unit` no longer doubles a unit ("%%"); sign hyphens in caller
  text are drawn as "−"; `relate(unit=)`; `x_unit=` and stricter bracket parsing;
  a crowded reference label moves to the end-label column; compare value labels
  are nudged off reference lines (`value_label_on_reference`); `too_tall`
  compresses panels first and then names the tallest panel and a concrete
  layout; `change` wraps and drops left labels in narrow columns; `share` stops
  "Share of Share of", states each highlighted part, wraps long names; grouped
  `relate` leads with per-group r and gives slope 95% CIs (`_t975`); crossings
  within noise are ignored; spikes stated against the median; matrix column
  means and an outlier cell; visible grey replicates; every size-limit error
  names its limit. SKILL.md: "stop at Publication Figures", a Limits and sizes
  block with measured heights, recipes.
- Cycle 2: alt text covers every group/series; `unit_is_long` warning; one
  "usual level" for an event-marked spike; unsigned ratios on log compare;
  unsigned spreads; reciprocal slope units ("MPa·µm½"); fold-change units.
  Recipes rewritten as domain-neutral patterns (r3 agents said recipes "matched
  the task exactly", i.e. the docs were leaking the benchmark).
- Cycle 3: compare intervals stated against `reference=` and against each
  other (which neighbours overlap); `compare(n=)`; signed compare facts against
  zero; no ratio facts on `zero=False` dot plots; log–log power-law exponents
  with CI; one fact summarising grey context series; units on every value in
  facts. SKILL.md step 4 lists what each form's facts compute and says not to
  refit or import scipy for them.

Left over from the runs (not fixed):
- Agents still recompute what facts already state (3 of 15 in r5): the step-4
  list is not read closely. Ideas: print the facts list in `ExplainError`-free
  form at the top of SKILL.md, or have agents read `fig.summary()` before saving.
- No check compares numbers in the takeaway and titles with the facts; r5/09
  shipped "22 points" where the facts said 18.5. A `number_not_in_facts` warning
  is the strongest next idea.
- Agents stop at the first pass and often never open the PNG; titles overclaim
  slightly ("clearly hurts" with overlapping seeds).
- Minor: no sub-grid peak position fact; fraction vs percent guidance; whether
  `x_unit` applies to date x; a recipe for compare + a two-series trend within
  the 4-colour limit; scipy is not available in agent environments.
- The benchmark runs with a pandas-equipped venv outside the repo; give it its
  own environment before relying on it. `runs/` keep only `results.md` in git.

## 4d. Fourth pass: review, GitHub gallery, and rough-edge fixes

Reviewed commits `5aa665e` and `fa9ebcf`, probed all seven `fm.explain` forms
across 14+ edge-case figures (inspected visually and with `bench.audit_layout`),
fixed eight newly surfaced rough edges, and built a full GitHub gallery.

Fixes applied in `src/figmint/explainer.py` (with `SKILL.md` updated and 6 new
regression tests in `tests/test_explain_final.py`, 521 tests total):

1. **`fm.relate` log-axis clipping & point-label clearance:** highlighted points
   (`names=` + `highlight=`) were scattered *after* `autoscale_view()` and
   `set_xlim`/`set_ylim`, clipping extreme highlighted points completely off the
   canvas on `log_x=True` or `log_y=True` with `ok=True` and `issues=[]`. They
   are now scattered before autoscaling, and a candidate-offset finisher keeps
   highlighted point labels clear of fitted lines (`_fit`) and axes bounds.
2. **`latex_markup` warning:** Matplotlib-habit `$...$` math (e.g. `$R^2 = 0.99$`,
   `$\mu\mathrm{M}$`) previously rendered literally with no warning. `explain()`
   now emits a `latex_markup` warning with a Unicode `fix_hint` without flagging
   currency like `$10M`.
3. **`share(highlight=...)` folded-item hint:** highlighting a valid part that
   fell below `top=` previously said "not in the data"; it now explains that the
   part was folded into `"Other (n)"` and states the exact `top=` needed.
4. **`compare()` signed ratio suppression:** `"auth is 2.0× the next highest"`
   was still emitted on signed/diverging data (e.g. `−190 ms` to `+2 ms`); now
   suppressed when `diverging` is true.
5. **`distribution()` signed-range `%` suppression:** when values cross zero,
   `baseline=` facts no longer print near-zero percentage blow-ups (e.g. `+6500%`
   against a `0.05` control median).
6. **`_range_with_unit` negative bounds:** ranges with a negative bound now use
   `" to "` (`"−1.7 to −1.1%"`) instead of colliding an en-dash and minus sign
   (`"−1.7–−1.1%"`).
7. **`trend(points_label=...)`:** optional label for `points=` dots (default
   `"replicates"`), carried through the spec and documented in `SKILL.md`, so
   non-replicate dots (tasks, wells, patients) do not force `"dots: replicates"`.
8. **`matrix()` missing (`NaN`) cells:** empty cells now render with a subtle
   neutral tint and a centred em-dash (`—`) instead of blending invisibly into
   the white canvas.

GitHub gallery additions (without overwriting any tracked `gallery/output/*` files):
- `gallery/explain_form_gallery.py` → `gallery/output/explain_forms/` (8 new
  clean PNG + JSON examples covering signed/CI `compare`, ISO-date/event/gap
  `trend`, log-log `trend`, `points_label=` `trend`, log `distribution`, grouped
  and log-log `relate`, and missing-cell `matrix`; all 8 pass `ok=True`,
  `issues=[]`, and `bench.audit_layout`).
- `gallery/README.md`: full visual showcase for GitHub covering every primary
  function (`fm.explain`, `fm.compare`, `fm.trend`, `fm.change`,
  `fm.distribution`, `fm.relate`, `fm.share`, `fm.matrix`), all four styles,
  `fm.load` / CLI, and publication plates (`fm.figure`, `fm.Plate`).
- Root `README.md`: added a visual 2-column primary-function gallery grid plus a
  before/after publication preview linking to `gallery/README.md`.

Additional review notes (not changed):
- `evals/figure_bench/.gitignore` ignores `runs/*/results.json`, so
  `make_progress.py` cannot be re-run from a fresh clone without committing
  those small JSON files (or reading `results.md`).
- A naive `number_not_in_facts` warning would false-positive on unit conversions
  (`0.01 µM` → `10 nM`), point deltas (`0.08` → `8 points`), version numbers
  (`v2.3`), and rounded estimates (`~460`), breaking `figure-bench`'s zero-warning
  gate; design it carefully or expose `fig.summary()` earlier in the agent loop.
- `src/figmint/explainer.py` is now ~8,100 lines and remains the top refactoring
  candidate.

## 4e. Fifth pass: `fm.histogram` / `distribution(bins=)`, themes & palettes, and README redesign

Added binned histogram support, expanded themes and color palettes, and redesigned
both `README.md` and `gallery/README.md` as visual first impressions on GitHub:

1. **`fm.histogram` & `fm.distribution(..., bins=...)`:** `distribution()` now
   accepts `bins="auto"`, an integer `2–60`, any numpy bin estimator, or explicit
   sorted bin edges (with log-spaced bins when `log=True`). Single-variable inputs
   draw a crisp vertical histogram with dashed median/mean marker and optional
   `reference=`; 2–4 groups draw shared-axis stacked small multiples (never muddy
   overlapping bars). Facts report bin count/width, each group's peak bin, and
   `% above reference`. `fm.histogram(values, bins="auto", ...)` is exported as a
   first-class alias (and `"kind": "histogram"` works in JSON specs).
2. **Three new built-in themes (`style=`):** `dark` (slate charcoal `#14181F`
   ground for dark UIs/slides), `paper` (warm ivory `#FAF7F0` with serif headlines),
   and `mono` (monochrome print with a single vermilion highlight accent), bringing
   `THEMES` to 7 (`figmint`, `bold`, `editorial`, `paper`, `dark`, `mono`, `sketch`).
   Fixed `preflight._check_text_on_data` to measure ink relative to the axes/figure
   background (supporting transparent axes and dark grounds) and matrix cell text
   contrast on dark grounds.
3. **Independent color schemes (`palette=`):** added `EXPLAIN_PALETTES` (`default`,
   `okabe_ito`, `tol`, `earth`, `ocean`, `berry`) in `themes.py`, wired into
   `fm.explain(..., palette=...)`, `to_spec()`, `summary()`, `explain_from_spec()`,
   and CLI `figmint explain --palette`, with automatic contrast lifting on dark
   grounds. Every theme and palette is verified in `tests/test_explain_styles.py`
   for deuteranopia, protanopia, grayscale separation (`>= 0.05`), and WCAG 4.5:1
   text contrast.
4. **Gallery & README redesign:** added `histogram_bimodal` and `histogram_groups`
   to `gallery/explain_form_gallery.py`, added `gallery/explain_theme_palette_gallery.py`
   → `gallery/output/explain_themes/` (all 7 styles, all 6 explain palettes, and
   `palettes_overview.png`), put compact visual thumbnails for every primary form
   directly in the main `README.md` table plus the palette overview card, and
   expanded `gallery/README.md` with full theme & palette side-by-side grids.

## 4f. Publication path: lines past the axis (README's first example)

The README's first figure (`before_after_nature.png`, example 1 in
`gallery/generate_showcase.py`) passed preflight while its dashed 50% line,
drawn with `ax.axhline`, ran ~54 pt past the end of the x axis into the
direct-label gutter: `direct_labels(expand_xlim=...)` widened the axes and the
spine was trimmed back, but full-width lines followed the new limits, and no
check looked at line geometry (`canvas_clipping` covers text only).

- New preflight check `line_past_axis` (`_check_lines_past_axes`, a **fail**):
  every `Line2D`, `LineCollection` and `PolyCollection` must stay within its
  axis lines (spine extents, including `set_bounds` trims) and the canvas.
  Marks drawn in the margin on purpose carry gid `figmint-margin`
  (`annotations.MARGIN_GID`; `range_frame` rugs do) and are skipped. No false
  positives across the 35 `evals/corpus` scripts or showcase examples 2 and 3.
- `direct_labels` now bounds full-width `axhline`s to the original x range
  before widening it (`_bound_full_width_lines`).
- Example 1: units drawn upright (Greek mu U+03BC; Helvetica's micro sign is
  slanted and mathtext's `\mu` sits in the italic slot), `IC$_{\mathrm{50}}$`,
  and the caption's preflight tally is computed from the report instead of a
  hard-coded "8/8".
- Tests: four in `tests/test_preflight_regressions.py`.

## 4g. Sixth pass: audit-gated `ship`, tidy tabular inputs, `fm.table`, and progressive `SKILL.md`

Modular seams added outside `explainer.py` (preparing for the upcoming `explainer.py`
split and model-release chart extensions):

1. **Promoted drawn-layout audit into `figmint` (`src/figmint/audit.py`) and `ship`:**
   - Exported `fm.audit_figure(fig)` and `fm.audit_layout(png)` implementing the
     drawn-text overlap, line-striking-text, and text well-formedness (`%%`,
     repeated words, ASCII hyphen minus, `nan`/`None`/`inf`) checks.
   - Wired `audit_figure` into `explain()` (respecting `theme.minus_sign == "-"`
     for `sketch`) and fixed the dead `"text_collision"` rule name in
     `_VISUAL_DEFECT_RULES` → `"text_overlaps"`, plus `"text_struck_by_line"`,
     `"text_malformed"`, and `"line_past_axis"`.
2. **Tidy / row-shaped tabular inputs (`src/figmint/_tabular.py`):**
   - Fixed raw `KeyError: 0` on `fm.compare([{...}, {...}])` and unhelpful
     `fm.trend(x, rows)` hints; both now raise clear `ExplainError` messages
     listing columns / pivoting / `data=`.
   - Added zero-pandas tidy support across all forms (`list[dict]` and duck-typed
     `pandas.DataFrame`): `compare`/`share` (`name=`, `value=`, 2-col auto-infer,
     plus column-name `error=` and `n=`), `trend` (`"x_col", "s_col", y="y_col",
     data=rows` with automatic `points=` replicates and column-name `band=`),
     `change` (`"col1", "col2", data=rows, name="item"`), `distribution`/
     `histogram` (`group=`, `value=`), `relate` (`data=rows` with column names),
     and `matrix` (`rows="r", cols="c", value="v"` auto-pivot).
3. **Structured table form (`src/figmint/_table.py` → `fm.table`):**
   - Booktabs-styled exact lookup & scorecard panel supporting `list[dict]`,
     DataFrames (preserving meaningful index), `{col: [...]}`, and 2-D lists +
     `columns=`, with `units=`, `highlight=` (shared entity colour across panels),
     `baseline=`, `bold_best=` (`True`/`"max"`/`"min"`/`{col: ...}`), `sort=`,
     `align=`, `fmt=`, muted `—` for missing cells, computed `facts`, PNG spec
     round-tripping, lenient `table_too_wide` auto-stacking, and
     `panel.to_markdown()`.
4. **Progressive `SKILL.md` + Cursor `.mdc` fix (`src/figmint/skill.py`, `pyproject.toml`):**
   - Slimmed `SKILL.md` from 29.7 kB (~7.5k tokens; 23.9 kB chat section) to
     9.8 kB (~2.2k tokens), added the `pip install` bootstrap line, and moved
     deep scientific recipes & publication details into
     `src/figmint/assets/references/{scientific_and_recipes,publication}.md`
     (installed alongside `SKILL.md` for `claude`/`antigravity`/`codex` and
     bundled in wheel/sdist).
   - Updated `_build_cursor_mdc` description and globs (`**/*.py`, `**/*.csv`,
     `**/*.json`) so Cursor triggers on chat figures and tables, not just
     publication scripts.

## 4h. Seventh pass: modular `_explain` split & frontier model-release chart suite

1. **Modularized `explainer.py` (9,237 → 145-line compatibility facade):**
   - Split cleanly into `src/figmint/_explain/` (`core.py`, `compare.py`,
     `compare_grouped.py`, `trend.py`, `change.py`, `distribution.py`,
     `relate.py`, `matrix.py`, `layout.py`) with a strict DAG dependency
     structure and module `__getattr__` on `figmint.explainer` preserving 100%
     backwards compatibility with all external callers and tests.
2. **Grouped & stacked-boost `fm.compare`:**
   - Nested `{category: {series: val}}` dicts and tidy `group=` rows draw
     grouped horizontal bars / Cleveland dots with a frameless inline colour
     strip, shared entity colours across panels, win-tally & baseline-gap
     `facts`, and full spec round-tripping.
   - `boost=` + `boost_label=` draw tinted stacked extensions (e.g. standard +
     extended thinking), sorting by total, printing total + `(+delta)` labels,
     and emitting `boost_unlabelled` if unnamed.
3. **Pareto frontier, `label_all`, and trajectories on `fm.relate`:**
   - `frontier=True` / `"upper-left"` | `"upper-right"` | `"lower-left"` |
     `"lower-right"` computes and draws the exact non-dominated Pareto envelope
     and lists frontier items in `facts`.
   - `label_all=True` (with `names=`, ≤24 points) labels every point with
     multi-candidate collision avoidance against lines, axes bounds, and group
     labels.
   - `connect_groups=True` connects points within each group in x order.
4. **Release-card styling (`accent=` & `width="slide"`):**
   - `apply_accent(theme, accent)` in `themes.py` + `accent=` on `fm.explain` /
     `--accent` in CLI pins a custom brand accent hex (contrast-checked for dark
     and light grounds).
   - `width="slide"` targets a 1280 px display width (exporting 2560 px at
     `scale=2.0`) with zero false `small_at_chat_size` warnings while keeping
     `width="chat"` / `width="wide"` chat-column behavior unchanged.

## 4i. Eighth pass: harness-adaptive delivery, visual-science upgrades & epistemic auditing

1. **Harness-adaptive delivery (`interactive.py`, `terminal.py`, `cli.py`, `width="narrow"`):**
   - `width="narrow"` (92 mm / 450 px target width in `specs.py` & `layout.py`)
     targets 420–480 px IDE sidebars (Cursor / VS Code), auto-stacking
     multi-panel layouts vertically (`[["a"], ["b"], ...]`) while keeping
     `min_text_px >= 12.1` px (≥11 px floor).
   - `src/figmint/interactive.py` (`fm.render_html`, `render_html_fragment`,
     `Explanation.to_html()`, `Explanation._repr_html_()`, `fig.save("out.html")`,
     and `figmint explain ... --out out.html`) emits zero-CDN self-contained
     HTML with inline SVG, theme-matched light/dark surfaces, toggleable Facts
     & Data drawer, Download SVG, Copy Spec JSON, and a Critique / Ask Agent
     feedback snippet builder.
   - `src/figmint/terminal.py` (`fm.render_terminal`, `fm.show_in_terminal`,
     `Explanation.to_terminal()`, and `figmint show <path_or_spec>`) detects
     Kitty/Ghostty APC and iTerm2/WezTerm OSC 1337 inline PNG protocols and
     falls back to crisp Unicode/ASCII bars, box-drawn tables, and sparklines.
2. **Visual-science form upgrades (`_explain/{distribution,compare,trend,relate}.py`):**
   - `distribution(mode="quantile", quantiles=20)` renders Wilkinson-stacked
     countable quantile dotplots; both modes emit exceedance probabilities above
     `reference=` and empirical superiority `P(group > baseline)` facts.
   - `compare(inner_error=..., show_delta=True)` renders nested inner/outer
     intervals (Kay & Hullman) and inline signed baseline deltas beside value
     labels.
   - `trend` and `relate` gain shaded `regions=[(x0, x1, label)]` and
     collision-aware direct leader `callouts=[(x, y, note)]` (≤4).
3. **Four-level semantic narrative & advisory epistemic audit (`epistemic.py`):**
   - `fm.build_narrative` (Lundgard & Satyanarayan L1–L4 + compact `summary`)
     is wired into `summary["narrative"]`.
   - `fm.audit_epistemic` runs inside `fm.explain()` emitting advisory-only
     `severity="warning"` issues (`claim_overstates_uncertainty`,
     `claim_number_mismatch`) kept outside `_VISUAL_DEFECT_RULES` so they never
     falsely block `ship`, verified at zero false positives across all gallery
     examples and existing tests.
4. **Exports & docs:** exported `render_html`, `render_terminal`,
   `show_in_terminal`, `build_narrative`, and `audit_epistemic` on `figmint`
   and `figmint.explainer`; updated compact `SKILL.md` and
   `references/scientific_and_recipes.md`.

## 5. Verified at the end of this pass, and what was not

Verified:

- **Non-strict / fast-shipping mode (added right after pass 5):**
  - `summary["ship"]` boolean (in both strict and lenient modes) separates real
    visual defects (`_VISUAL_DEFECT_RULES`) from advisory polish warnings so
    agents ship good-enough figures on the first try without extra re-render loops.
  - `with fm.lenient():`, `fm.explain(..., strict=False)`,
    `fm.explain_from_spec(..., strict=False)`, and CLI `figmint explain --lenient`
    (`--no-strict`) auto-adjust soft limits instead of raising `ExplainError`
    (auto-faceting >4 trend series, trimming >20 compare items / >14 change items
    / >8 distribution groups / >3 highlights, dropping NaN / unmatched items,
    resolving baseline-in-highlight, wrapping long takeaways, auto-stacking
    cramped side-by-side panels into full-width rows, falling back on unknown
    style/palette), logging every change in `summary["adjustments"]` and moving
    advisory nudges into `summary["advisories"]`.
  - Updated `SKILL.md`, `AGENTS_SNIPPET.md`, and `README.md`.
- `pytest`: 742 passed. `ruff check src tests gallery evals`: clean.
- All six general figures in all four styles, and the five scientific figures,
  render with `ok: true`, no issues, smallest text 12.3 px. The general set is
  also clean with only DejaVu Sans available (a stand-in for a Linux host
  without Helvetica; `test_reference_set_is_clean_with_only_dejavu_sans`).
- Forty edge cases (pandas inputs, scalar errors, bands, dates, NaN, duplicate
  x, typos in argument names, Greek and super/subscript text) end in either a
  clean render or an `ExplainError` with a fix; no raw exceptions.
- Blind re-tests with the rewritten `SKILL.md`: the dose-response question
  took one render with no issues (before: three renders and four failed
  argument guesses); the materials question took seven renders for three
  figures, each exception telling the agent exactly what to change. Their
  remaining requests were folded into the last fix round (facts in ratios and
  slopes on log panels, small-n cautions stated once, consistent significant
  figures) or recorded below.
- `uv build` produces a 125 kB wheel and a 150 kB sdist (code, tests, docs).

Not verified:

- No run on an actual Linux host or in CI; only the DejaVu-only simulation.
- The publication path was not re-reviewed; its tests pass and the one
  preflight change is described in section 4. The repair eval was not re-run.
- No reader study: whether people read these figures faster or more correctly
  than hand-made plots is untested (section 6, item 2).
- The committed `gallery/output/explain*` renders predate the second and third
  passes: the code that draws them changed (date ticks, labels, facts).
  Regenerate them only with the owner's OK (they overwrite tracked files).

Known limits:

1. Superscripts are drawn at 70% of the label size (about 9 px at chat width),
   below the 11 px floor; reported as `display.min_script_px`, not enforced.
2. `trend` has no `fit=`; an agent computes slopes itself, though log-axis
   facts now report the log-slope and R² per series.
3. More than four ordered levels (doses, doping levels) get three colours and
   grey context; there is no sequential ramp for lines.
4. `relate` takes at most four groups.
5. Log axes extend to the next labelled decade, which can leave up to a decade
   of empty space above the data.
6. A character in a mathtext run that the body font lacks comes from the
   fallback font at normal weight, so it looks light in a bold title.
7. `fm.custom` bypasses the form rules (preflight still runs).
8. Left over from the second blind tests (not fixed): `colors=` pins by exact
   name, so "us-west after" does not inherit "us-west"; grey context names at a
   crowded line end are stacked, not attached to their lines; the thick
   centre tick in `distribution` can hide tight dots; a correlation matrix
   draws its diagonal in the darkest colour and shows both triangles; `relate`
   calls r = 0.48 "weak"; a `change` slopegraph with near-identical values
   overlaps; a long panel title wraps with no warning.

## 6. Next steps, in order

1. **Bet 4 (Human & VLM Comprehension Benchmark) — priority for next cycle:**
   - Build a reader-comprehension benchmark evaluating both VLMs and humans on
     factual accuracy, uncertainty calibration, and speed against hand-written
     baseline plots of the same data.
   - Include **harness-width evals** comparing legibility and answer accuracy
     across `450 px` narrow IDE sidebars (`width="narrow"`), `700 px` chat
     columns (`width="chat"`), and `1280 px` slide/hero cards (`width="slide"`),
     plus ablations for quantile dotplots, nested CIs, inline deltas, and
     direct callouts/regions.
2. CI with a Linux font-fallback job, and a release under whatever PyPI name
   the owner picks.
3. `trend(fit=...)` for linear and log-linear fits with the slope on the plot.
4. The visual leftovers in section 5, known limit 8, then regenerate the
   `explain*` gallery (with the owner's OK).
5. figure-bench: more held-out tasks (the core set has plateaued at ~20 s),
   narrow-sidebar & HTML-output tasks, and a dedicated venv.

## 7. Decisions

Settled (do not reopen without asking the owner):

- CLI + JSON + `SKILL.md`, not MCP. Distribution is `figmint skill --install`.
- Precision over rule count: deterministic checks are errors, heuristics are
  warnings, repair loops are capped at 2.
- Script contract for `figmint run`; exit codes 0, 1, 2.
- JSON `schema_version: "0.2"`: add keys, never rename or remove them.
- Versioned journal specs with source URLs.
- Neutral style names.

Open, for the owner:

- The PyPI distribution name (section 2).
- Seven built-in forms, now with scientific arguments, go further into an
  earlier "defer large plotting-recipe suites" decision. The set is still one
  form per question; confirm the scope.
- Whether `sketch` should keep warning on data not marked illustrative.
- Whether chat figures should offer a dark variant.
- Carried over: the global style leak in `Plate`/`fm.figure`; `turbo` not on
  the banned list; journal widths not checked against the publishers; whether
  to regenerate the stale publication plates and `evals/output/`.
