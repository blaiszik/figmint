# `mintfig` 1.0 Stability & Deprecation Policy

This document defines the stability contract for `mintfig` starting at `1.0.0`, how deprecations work, what stays internal, and the checklist remaining between `0.3.x` and `1.0.0`.

## Versioning

`mintfig` follows [Semantic Versioning 2.0.0](https://semver.org/) (`MAJOR.MINOR.PATCH`):

- **Patch (`1.x.y → 1.x.(y+1)`)**: bug fixes, false-positive reductions in `mint.check`, typography/layout fixes, and documentation updates with no breaking API or schema changes.
- **Minor (`1.x.0 → 1.(x+1).0`)**: backwards-compatible additions — new chart forms, themes, journal presets, optional parameters with backwards-compatible defaults, new CLI flags, and additive JSON fields.
- **Major (`1.x → 2.0.0`)**: breaking changes to any covered surface below, preceded by a deprecation window.

During `0.3.x` (pre-1.0), minor releases may still refine APIs when needed, though we keep top-level ergonomics stable and announce any breaking changes in `CHANGELOG.md`.

---

## Covered by the 1.0 SemVer Contract

### 1. Python API (`mint.*` & public submodules)

- Every symbol exported in `mintfig.__all__` (`import mintfig as mint`), including:
  - Auditing: `mint.check`
  - Explaining & composition: `mint.explain`, `mint.compare`, `mint.trend`, `mint.change`, `mint.distribution`, `mint.histogram`, `mint.relate`, `mint.share`, `mint.matrix`, `mint.table`, `mint.waterfall`, `mint.timeline`, `mint.flow`, `mint.custom`, `mint.lenient`
  - Editing, round-trip & briefings: `mint.load`, `mint.edit`, `mint.brief`, `mint.Brief`, `mint.Session`, `mint.notebook`
  - Data helpers: `mint.inspect_data`, `mint.auto_panel`, `mint.load_table_file`
  - Publication plates: `mint.Plate`, `mint.figure`
  - Core types: `mint.Explanation`, `mint.Panel`, `mint.ExplainError`
- Documented public submodules: `mintfig.pub`, `mintfig.themes`, `mintfig.audit`, `mintfig.skill`, `mintfig.pr_card`, `mintfig.notebook`, and `mintfig.interactive` / `mintfig.terminal` public entry points.
- Keyword parameter names and default meanings on these public functions will not break within a major version.
- **Deprecated (scheduled for removal in `2.0.0`)**: legacy `mint.inline` and `mint.InlineGraphic` remain functional for backward compatibility, but new word-sized inline graphics, shared-scale tables, and `{{...}}` prose directives live in the standalone [`mintchip`](https://github.com/blaiszik/mintchip) package (`pip install "mintfig[chip]"` or `pip install mintchip`).

### 2. CLI Subcommands, Flags & Exit Codes

All documented `mintfig` CLI subcommands (`check`, `explain`, `plot`, `edit`, `brief`, `inspect`, `show`, `run`, `specs`, `doctor`, `log`, `skill`, `hook`) and their documented flags follow SemVer.

Exit codes are part of the contract for CI, hooks, and scripts:

| Exit code | Meaning |
| :--- | :--- |
| `0` | Success: every figure/PDF passed (`ship: true` / `passed: true`). |
| `1` | Action required: one or more figures returned `FIX FIRST` / preflight failure (or warnings under `--strict`). |
| `2` | Usage, spec, or execution error: invalid CLI arguments, rejected spec, missing file, or unhandled exception in a checked script/notebook. |

### 3. JSON Output & `schema_version` (Additive-Only Rule)

Structured JSON payloads returned by `Explanation.summary()`, `mint.check()`, `mintfig check --json`, `mintfig explain`, and `mintfig run --json` carry a top-level `schema_version` string.

Within a major release (`1.x`):

- **Additive-only**: new keys, issue rules, or advisory codes may be added at any time.
- **No silent breakage**: existing documented keys (`ship`, `ok`, `issues`, `claim`, `display`, `panels`, `deliver`, `takeaway`, `fix_hint`, etc.) will not be removed, renamed, or change their value type.
- **Schema bumps**: any incompatible JSON structure change increments `schema_version` and ships only in a new major release.

### 4. Embedded `mintfig:spec` PNG Round-Trip Guarantee

PNG files written by `Explanation.save(..., embed=True)` (the default) embed a `mintfig:spec` iTXt metadata chunk.

- Any PNG produced by `mintfig 1.x` is guaranteed to load and re-render via `mint.load(png_path)`, `mint.edit(png_path, ...)`, and `mintfig explain <png_path>` across all later `1.x` releases without data loss.
- Optional new spec keys introduced in later `1.x` releases carry backwards-compatible defaults so older `1.x` specs round-trip cleanly.

---

## Deprecation Policy

When a public symbol, CLI flag, or behavior is scheduled for removal or replacement:

1. **Minimum 2-minor-release window**: the deprecated interface remains functional and emits a Python `DeprecationWarning` (or stderr deprecation notice for CLI flags) for **at least 2 minor releases** before removal.
2. **Actionable warnings**: every deprecation warning states what is deprecated, the exact replacement, and the target removal version, and is recorded in `CHANGELOG.md`.
3. **Major-version removal**: within `1.x`, deprecated public interfaces are not removed until `2.0.0` (satisfying both SemVer and the 2-minor-release window).

---

## Explicitly Outside the 1.0 Stability Freeze

The following areas may evolve in minor or patch releases without a major version bump:

- **Private & internal modules**: everything under `mintfig._explain.*`, `mintfig._inline.*`, `mintfig._check_runner`, `mintfig._table`, `mintfig._tabular`, and any underscore-prefixed function, class, or attribute.
- **Experimental evaluation harnesses & demos**: `evals/` (including `figure-bench`, `check-bench`, trigger evals), `gallery/`, and `promo/`.
- **Exact raster pixel identity**: `mintfig` guarantees layout legibility (`min_text_px`, zero overlaps/clipping) and semantic consistency, not bit-identical PNG bytes across different Matplotlib, FreeType, Pillow, or OS font versions. (PDF byte-reproducibility holds under pinned Matplotlib with `PYTHONHASHSEED=0`.)
- **Human-readable prose**: exact phrasing of `format_report()`, `message`, and `fix_hint` strings may be tightened to improve clarity; automated callers should match on structured `rule`, `severity`, `ship`, and `ok` fields.
- **Journal spec refreshes**: official journal column widths, font limits, or DPI guidelines in `mintfig specs` are updated when publishers revise author guidelines (tracked via `spec_version` and `last_verified`).

---

## Checklist: `0.3.x` → `1.0.0`

- [ ] **Check accuracy bar**: `mint.check` maintains `< 2%` false-positive rate and `> 90%` defect catch rate on the Wild-50 verification corpus across Matplotlib and Seaborn artists.
- [ ] **Top-level API & CLI audit**: verify every symbol in `mintfig.__all__`, public submodules, CLI flags, and exit codes `0`/`1`/`2` has complete docstrings, type annotations, and tests.
- [ ] **JSON schema lock**: finalize `schema_version: "1.0"` across `Explanation.summary()`, `mint.check`, `mintfig check --json`, `mintfig explain`, and `mintfig run --json` with schema regression tests.
- [ ] **Round-trip spec compatibility suite**: freeze a golden fixture set of `mintfig:spec` PNGs and JSON specs tested in CI for lossless `mint.load()` / `mint.edit()` round-tripping.
- [ ] **CI & PR workflow verification**: dogfood `.github/actions/mintfig-check` and `mintfig.pr_card.save_pr_card` in CI across Ubuntu and macOS on Python 3.10–3.13.
- [ ] **Clean up pre-1.0 shims**: review `_MOVED` attribute helpers and any legacy aliases; decide which remain as `DeprecationWarning`s vs clean `1.0` cuts.
- [ ] **Release notes & migration guide**: publish `0.3.x → 1.0.0` upgrade notes and tag `v1.0.0` with wheel + sdist smoke tests.
