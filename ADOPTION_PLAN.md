# Adoption plan: from "nice tool" to "used by thousands"

Written 2026-11-25 (updated 2026-11-26 after Phases 1–2). Current estimate: ~6/10
likely to reach thousands of users (up from 4/10). The goal is to remove the
reasons a person or an agent would choose plain Matplotlib instead, and to give
everyone else a concrete reason to switch.

## The pitch, restated

The real competitor is "the agent writes Matplotlib". That falls short in three
ways mintfig already fixes:

1. It doesn't communicate complex results. There's no single claim, uncertainty
   goes unnamed, and the panels don't add up to an argument.
2. The default styling is off-putting. There are legend boxes, clipped and tiny
   text, mismatched colours across panels, and it looks wrong at chat width.
3. The figure isn't tied to any facts. Nothing checks the number in the reply
   against the data, so the figure can quietly disagree with what the agent says.

One-line pitch: **figures whose claims are checked against the data, and that
look good by default.** Every workstream below either proves that or makes it
cheaper to adopt.

## A. Make the rules defaults, not bans

"No legends, no pies" was never the owner's rule. Keep the defaults that are well
supported, and let users opt out of the matters of taste.

| Today | Change | Why |
| :--- | :--- | :--- |
| `legend=` raises "There are no legends" (`_explain/core.py:686`) | `legend=True`, plus an automatic legend when direct labels would collide (dense trends, `relate` with groups). Direct labels stay the default. | Legends are expected in many fields, and their absence reads as a bug. |
| `share` never draws a pie | `share(kind="pie" \| "donut")` for at most 5 parts, with an advisory when two parts are within ~5 points (angles are hard to compare) | Executives, clinicians and biologists expect pies for a 2–4 part split. |
| Dual axes are banned | Keep the ban (it genuinely misleads). The error already suggests `facet=`. | Evidence is strong. |
| Rotated text is banned | Keep it; the horizontal layouts make rotation unnecessary. | Not a real constraint today. |

Principle: **an error means the figure would be wrong** (unlabelled scale, a
truncated bar baseline, rainbow colormaps, text overlap). **An advisory means it's
a matter of taste.** Audit every `ExplainError` against that line. The README's
rules table becomes "defaults and their sources".

## B. Bring your own Matplotlib (biggest adoption lever)

Most people, and most agents, already have Matplotlib code. Today the only way in
is to rewrite it into one of the eleven forms. Make mintfig a layer they add, not
a library they switch to:

- [x] **B1 `mint.style()` (shipped 2026-11-26):** leak-free context manager in `src/mintfig/byo.py`
  giving any Matplotlib/Seaborn plot chat-readable sizing (>=11 px), CVD-safe palettes, despining,
  and `viridis` default cmap.
- [x] **B2 `mint.explain(takeaway, fig_or_ax)` (shipped 2026-11-26):** accepts any existing
  Matplotlib `Figure`, `Axes`, or `SubFigure` as a panel, runs `mint.check` facts & audit, and
  wires `ship`, `deliver`, HTML, terminal, and `mint.brief` (`gallery/byo_matplotlib_examples.py`
  upgrades 5 ugly scripts to `ship: True` in 1–2 lines).
- [x] **B3 Facts from artists & zero-rewrite audit (`mint.check`, `mintfig check`):**
  - Shipped 2026-11-26: `mint.check(fig, claim)` and `mintfig check plot.py` (facts from
    `Line2D`, `BarContainer`, `PathCollection`, error bars, plus Phase 1 hardening for
    `QuadMesh`/heatmaps, colorbar exclusion, histograms, `PolyCollection` CI bands,
    boxplots/violinplots, and false-positive filtering for model/precision tokens,
    sample counts, years, and unit conversions).
  - Shipped 2026-11-26: cross-venv `--python` / `uvx` auto-detection, zero-dep `.ipynb`
    notebook checking (`mintfig check analysis.ipynb`), and the Wild-50 verification
    corpus (`evals/check_bench/`).

Done when: a gallery of five ugly agent-written Matplotlib scripts each becomes
a shippable figure with facts by adding 1–2 lines (audit half done; B1 + B2 open).

## C. Prove it, against Matplotlib rather than against text

The README compares mintfig only to a text answer. The objection people actually
raise is "my agent already makes plots."

- [x] **C1 A Matplotlib arm in figure-bench (shipped 2026-11-25).** Ran the same 15 tasks
  with an agent told to use plain Matplotlib (`--arm matplotlib`, `--arm matplotlib-plain`)
  and scored headline accuracy, display-width text size, layout defects, unlabelled
  intervals, and time.
- [x] **C2 A three-column README opener (shipped 2026-11-26):** agent text | default agent
  Matplotlib (`13/15 defective, 4/15 accurate headline`) | `mintfig`, rendered from the
  same 5-variant, 5-seed ablation dataset via `gallery/make_readme_comparison.py`, with
  the wedge-first adoption ladder (`mint.check` + `mintfig hook` alongside `mint.explain`).
- [ ] **C3 Reader benchmark** (HANDOFF §6, item 1): factual accuracy and time for VLM
  readers at display size first, then 20–50 people, comparing text, agent Matplotlib and
  mintfig.

## D. Distribution

- [x] ~~Settle the PyPI name.~~ Settled 2026-11-26: `mintfig`, secured by the owner.
- [x] **Global skill install & full reference print (shipped 2026-11-26):**
  `mintfig skill --install --global` (auto-detecting `~/.claude`, `~/.codex`,
  `~/.gemini`, `~/.cursor`), `--target all`, and `mintfig skill --print --all`
  printing `SKILL.md` + all `references/*.md`.
- [x] **Automatic `PostToolUse` hooks (shipped 2026-11-26):** `mintfig hook --install`
  silently audits agent-written Matplotlib scripts and reports `fix_hint`s only when
  `ship` is `false`.
- [x] **Claude Code plugin packaging (shipped 2026-11-26):** `plugins/claude-code/`
  with synced `SKILL.md` + `references/`, `PostToolUse` hook config, and `/mintfig:check`.
  (Submission to public Claude Code / Codex / Cursor directories still open.)
- [x] **Trigger eval (shipped 2026-11-26):** 40 realistic prompts (20 positive, 20 negative,
  zero mentions of `mintfig`) in `evals/trigger_eval/` with offline rubric scorer,
  `--live` CLI adapter (`claude`, `codex`, `gemini`), and tuned `SKILL.md` /
  `AGENTS_SNIPPET.md` trigger criteria (exit gate: recall >= 85%, false-trigger <= 5%).
- [ ] Submit plugin and skill listings to Claude Code, Codex, and Cursor directories.
- [ ] Notebook, Quarto, and marimo examples in the gallery.

## E. Complex scientific topics where Matplotlib is weakest

Add forms that are tedious to get right by hand, and where agents get them
wrong: forest plots (effect and CI per study or subgroup), Kaplan–Meier curves
with an at-risk table, volcano plots with named hits, and spectra with peak
assignments. Each one computes facts like the existing forms do.

## F. Stability

Finish A and B, then freeze the API at 1.0 with a deprecation policy (the 0.3.0
clean break was fine before 1.0, but adopters need the promise). Add a
searchable gallery site organized by question and by field.

## Order

| Phase | Work | Status | Expected effect |
| :--- | :--- | :---: | :--- |
| 1 | C1 Matplotlib arm, C2 3-col README opener, B3 `mint.check` wild hardening (`--python`, `.ipynb`, Wild-50), settle PyPI name | **Done** (except A rule relaxation) | The objection gets a measured answer & zero-rewrite wedge |
| 2 | D global skill install, PostToolUse hooks, Claude Code plugin, 40-prompt trigger eval | **Done** | Zero-friction install, auto-audit, reliable triggering |
| 3 | A relax opt-in rules (`legend=`, `pie`/`donut`), B1 `mint.style()`, B2 `mint.explain(takeaway, fig)`, notebook magic, SWE ingestors + `mintfig diff`, PR cards + GitHub Action, 1.0 stability policy | **Done** | Adopting costs 1–2 lines; strong SWE & CI/PR utility |
| 4 | D public directory listings, C3 human reader study, E domain forms, F 1.0 API freeze + interactive gallery site | Open | Public proof, discoverability, and 1.0 trust |

## Decided (owner, 2026-11-25)

- Legends and pies become opt-in: `legend=True` and `share(kind="pie")` are
  allowed, direct labels and sorted bars stay the default, and there is no
  automatic legend switch.
- Build C1 + C2 (the Matplotlib arm in figure-bench and the three-column README
  opener) first.

## C1 result (2026-11-25)

Built and run: `evals/figure_bench` has `--arm matplotlib` (told the width and checks),
`--arm matplotlib-plain` (told neither), a neutral audit of the saved Figure for every
arm, `compare`, and blind readers (`readers-prepare` / `readers-score`). Results in
`evals/figure_bench/runs/compare_r6_b1_u1.md`:

- Measured advantage: an agent writing Matplotlib as it does today ships a layout or
  text defect in 13 of 15 figures (mintfig: 1 of 15), and mintfig headlines carry the
  answer (13/14 vs 4/15).
- Not shown: blind VLM readers at full resolution got the key number from every arm.
  The README must not claim figures are "read better" until C3 tests display-size
  images and people.
- Product fixes found: `low_density` should be an advisory; phone readers lead agents
  to `width="narrow"` (decide which is right for phones); put the `trend(points=)`
  shape in SKILL.md.

Rough effect on the score: phases 1–2 take it to about 5–6/10, and a published
reader result plus directory listings to about 6–7/10.
