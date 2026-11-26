# mintfig — presentation-layer plan

Written 2026-11-25 against `main` at `2032c5d` (0.2.1). Scope: everything between a
finished `Explanation` and the reader's eyes — the PNG, the HTML page, the terminal
text, the briefing, the summary the agent reads, and the public API an agent has to
remember. `mint.inline` (chips) is excluded: it is moving to its own package.

## 1. The finding in one paragraph

The static figure is already the strong part. Takeaway titles, direct labels, zero
baselines, named intervals, grey context and the drawn-text audit put a default
`mint.explain` PNG well ahead of what agents usually produce. The weak part is the
last mile. A figure only replaces a wall of text if it shows up **in the reply, at the
reader's real width and theme, in a medium the harness can display**, and today
mintfig stops at "a file was written". The secondary surfaces (HTML, terminal,
briefing) do not follow the rules the PNG enforces, and the top-level API has grown
to 91 names across two products. The plan fixes those three things first, then adds
four Tufte-driven upgrades to the figure itself.

## 2. Evidence (rendered and inspected in this pass)

All from the README's ablation example unless noted.

| # | Surface | What it does now | Principle it breaks |
| :- | :--- | :--- | :--- |
| 1 | `fig.save()` return | Returns `path` and `alt_text`. `SKILL.md` step 4 says "deliver" and never says how. Nothing tells the agent how to put the image in the reply for its harness. | The figure has to be seen to count |
| 2 | HTML at a 500 px viewport | The 700 px layout is scaled down, so axis and value labels land at about 7 px (12.3 px × 0.56). `width="narrow"` re-layout exists for PNG only. No `prefers-color-scheme` handling. | mintfig's own 11 px floor |
| 3 | HTML page | A static SVG in a card above a four-button toolbar (Facts & Data, Critique / Ask Agent, Download SVG, Copy Spec JSON), with two more copy buttons inside the critique drawer. No value on hover. | Data-ink; details on demand (Shneiderman) |
| 4 | Terminal `compare` | A panel drawn as dots with 95% CIs in the PNG becomes zero-based bars with no intervals. | Named uncertainty; one grammar per figure |
| 5 | Terminal `trend` | `0.02 → 0.82 (+4000%)`; every series the same blue; each sparkline scaled to its own range, so three different series print as `▁▆▇██`, `▁▆▇██`, `▁▅▇██`. | Lie factor; common scale (Cleveland) |
| 6 | Entity colour | "full model" is grey in panel a and green in panel b, while `summary["colors"]` reports green. | README rule "one colour per entity" |
| 7 | Markdown briefing | Each figure is followed by five bullets of raw facts with `[a]` prefixes. No prose between figures. | It rebuilds the wall of text beside the figure |
| 8 | Summary JSON | 4.1 kB for a two-panel figure; the same facts appear in `panels[i].facts`, `narrative.L2/L3` and `alt_text`. | Agent context is the scarce resource |
| 9 | `01_ablation_waterfall.png` | Deltas labelled `+8.2%` on an accuracy-% axis (the takeaway says "points"); the highlight accent is the same hue family as the negative step. | Percent vs percentage point; colour means one thing |
| 10 | `checkout_story.png`, `table_scorecard_chat.png` | Two of the four checkout panels restate one ranking (4–5 numbers each); the scorecard repeats a table column as a bar panel. | Data density; table-graphics |
| 11 | `import mintfig` | 91 exported names. Pairs that collide for an agent guessing: `mint.slopegraph` vs `mint.change`, `mint.figure` vs `mint.explain`, `mint.PALETTES` vs `mint.EXPLAIN_PALETTES`, `mint.get_palette` vs `mint.get_explain_palette`, `mint.use`/`mint.apply` vs `style=`. | Recognition over recall |

Not a problem: speed (import 0.28 s, CLI render 0.66 s) and static render quality.

Terminal output for row 4–5, verbatim (colour codes removed):

```
[a] Both losses are outside seed noise [Test accuracy]
        full model  █████████████████████████████████████████████████████ 0.82
  ▸   no retrieval  ███████████████████████████████████████████████▉ 0.74
  ▸ no fine-tuning  ████████████████████████████████████████████▋ 0.69
[b] The gap opens in the first 500 steps [Validation accuracy]
        full model  ▁▆▇██  0.02 → 0.82 (+4000%)
      no retrieval  ▁▆▇██  0.02 → 0.74 (+3600%)
    no fine-tuning  ▁▅▇██  0.01 → 0.69 (+6800%)
```

## 3. Design position

One `Explanation`, four surfaces — image, HTML, text, document — and **every surface
obeys the same rules or does not render that panel**. A surface that cannot show an
interval says "intervals not shown" and prints the bounds as numbers; it does not
draw a bar. The rule set already exists in `_explain/`; this plan extends its reach,
it does not add a second grammar.

The reader's environment (width, light or dark) belongs to the reader, not to the
agent that picked `style=`.

## 4. Work, in order

### Phase 1 — The last mile (do first; small, highest adoption value)

**1a. A delivery block on every save.** `summary["deliver"]`, additive under schema
0.2:

```json
"deliver": {
  "markdown": "![Removing retrieval costs 8 points …](ablation.png)",
  "caption":  "Both losses are outside seed noise (95% CI, 5 seeds).",
  "text":     "<plain-text rendering, no ANSI, ≤ 72 columns>",
  "html":     "ablation.html"
}
```

`markdown` uses a path relative to the working directory. `caption` is one sentence
chosen from the facts that support the takeaway, so the reply is *sentence, figure,
caption* and the facts list stays with the agent.

**1b. `SKILL.md` step 5, "Put it in front of the reader".** A five-row table: harness
→ what to paste (chat with image rendering → `deliver.markdown`; artifact-capable
host → the `.html`; plain terminal or unknown → `deliver.text` in a code block;
notebook → return `fig`; PR or issue → committed PNG plus the `<picture>` light/dark
snippet). Add a reply template of at most three lines of prose around the figure.

**1c. `mintfig doctor`.** Prints which surfaces work in the current environment
(inline-image protocol, fonts resolved, browser available) and renders one sample,
so a new user confirms delivery in under a minute.

**1d. Fix the text surface so it can be trusted as the universal fallback.** In
`terminal.py`:
- `compare` with `error=` prints dot-and-whisker rows on one shared axis
  (`├──●──┤`) with the interval label, never bars.
- `trend` sparklines share one y range across series; each series gets its own
  colour or none.
- Relative change is suppressed when the starting value is smaller than 10% of the
  series range; print the absolute change instead.
- Add `color=False` output that is safe inside a Markdown code block; `deliver.text`
  uses it.
- A panel kind with no faithful text form prints its title and top facts only.

Done when: the figure-bench layout audit gains a text-surface check (same ranking,
same intervals, no percentage from a near-zero base) and all gallery specs pass it.

### Phase 2 — HTML that earns being HTML

**2a. Responsive.** Lay the figure out at `narrow` and `chat` (0.17 s each), embed
both SVGs, and switch with a container query. The 11 px floor then holds at the
width the reader actually has.

**2b. Light and dark from one file.** Post-process the SVG so each theme token
becomes `var(--mf-…, <light hex>)` and set the dark values under
`prefers-color-scheme: dark`. Fallback if two tokens share a hex: embed a second SVG.
`style="dark"` stays available for slides, where the author does control the ground.

**2c. Details on demand, without chrome.** Give every mark a `gid`; a ~40-line
script shows the exact value, interval and n on hover or focus. Clicking a mark
copies a citation (`ablation.png · b · no retrieval @ 500 = 0.52`) the reader can
paste back to the agent. This replaces the Critique form: pointing at a mark is the
feedback people actually give.

**2d. Remove the toolbar.** One quiet line under the source: `data · svg · spec`.
The data table opens in place.

Done when: screenshots at 390, 500, 700 and 1280 px in both colour schemes pass the
existing `audit_layout` text-size check.

### Phase 3 — Four upgrades to the figure itself

**3a. Tie the words to the marks (Tufte: integrate text and graphic).**
- Entity names in the takeaway and panel titles are drawn in that entity's colour.
- When the takeaway states a difference, draw it: a bracket between the two marks
  with the number (`show_delta` exists on `compare`; generalise it and switch it on
  when the epistemic audit matches a takeaway number to a pair of marks).
- Fix row 6: an entity that is coloured anywhere in a figure is coloured everywhere,
  and a `baseline=` entity is ink everywhere.
- Fix row 9: deltas on a percent-unit axis are labelled `pts`.

**3b. Small multiples as a layout, not a `trend` option.** `facet=` on `compare`,
`distribution`, `histogram` and `relate`, shared scales by default. Add an advisory
`scales_differ` when two panels in one figure carry the same `label=` and unit with
different axis ranges.

**3c. Table-graphics.** `mint.table(bars=[cols], spark={col: series}, interval={col: (lo, hi)})`
draws an in-cell bar, sparkline or whisker beside the number, on one scale per
column. This removes the table-plus-bar-panel pattern (row 10). Drawn in Matplotlib,
no dependency on the chips package.

**3d. Density.** A `density="compact"` layout (thinner bars, tighter rows, smaller
panel gap) and an advisory `low_density` when a figure is taller than 320 px at
display size for fewer than eight plotted values, with the hint "use `mint.table`
or one sentence". Report `display.height_px` in the summary. Bank `trend` panel
aspect so the median segment slope is near 45° (Cleveland), within the existing
height limits.

Done when: the gallery regenerates clean (owner's OK needed — it overwrites tracked
files) and the two redundant-panel examples are rebuilt as one panel each.

### Phase 4 — A briefing that reads as a document

- `mint.brief(title, "prose", fig, "prose", fig, …)`: strings are paragraphs.
- Opens with one row of thumbnails, one per finding, each under its takeaway —
  the macro reading before the micro one.
- One caption per figure (`deliver.caption`); the facts move into a collapsed
  "numbers behind this figure" block in HTML and are left out of Markdown.
- Shared colour ledger (exists via `Session`) plus the `scales_differ` advisory
  across figures.
- Print stylesheet: one finding per page, no page break inside a figure.

### Phase 5 — Shrink the surface

Target: 91 top-level names → about 28. **Decided by the owner on 2026-11-25: move
now with no shims**, as a clean break in 0.3.0. A removed top-level name should fail
with an `AttributeError` that names its new home (`mint.direct_labels` →
`mint.pub.direct_labels`), and `README.md`, `SKILL.md`, `references/publication.md`,
the gallery scripts and `evals/corpus` move to the new names in the same change.

| Action | Names | Why |
| :--- | :--- | :--- |
| **Keep** top-level | `explain`, the 11 forms, `histogram`, `custom`, `Explanation`, `Panel`, `ExplainError`, `lenient`, `load`, `edit`, `Session`, `brief`, `Brief`, `inspect_data`, `auto_panel`, `load_table_file`, `Plate`, `figure` | What an agent calls |
| **Move** to `mint.pub` | 41 names: the 14 annotation primitives (`despine` … `zoom_inset`), `save_figure`, `rasterize_heavy`, `bundle_figure`, `BundleResult`, the 4 preflight names, `render_proof_sheet`, `run_script`, `RunResult`, the 6 journal-spec names, `apply`, `use`, `rc_params`, `resolved_font_name`, the 6 palette/colormap names | Publication-only; ends the name collisions in row 11 |
| **Move** to `mint.themes` | `THEMES`, `Theme`, `get_theme`, `EXPLAIN_PALETTES`, `ExplainPalette`, `get_explain_palette` | Reference data, not verbs |
| **Move** to `mint.audit` | `audit_figure`, `audit_layout`, `audit_epistemic`, `build_narrative` | They already run inside `explain()` |
| **Fold** into methods | `render_html`, `render_terminal`, `show_in_terminal` → `fig.to_html()`, `fig.to_text()`, `fig.show()` | One way to deliver |
| **Fold** into `load` | `explain_from_spec`, `panel_from_spec` → `mint.load(path_or_dict)` | One way to rebuild |
| **Move** to `mint.skill` | `install_skill`, `get_skill_markdown`, `get_agents_snippet`, `VALID_TARGETS` | The CLI is the interface |
| **Leave** the package | `inline`, `InlineGraphic` | Moving to its own package; it should import only public names (`mint.Explanation`, `mint.ExplainError`, `mint.themes`) |

Also:
- `pypdf` becomes the `mintfig[pub]` extra (only `preflight_pdf` needs it).
- Styles: keep all seven, but `SKILL.md` names three — `mintfig`, `dark`, `mono` —
  and reserves `sketch` for illustrative data. A recognisable default look helps
  adoption more than choice does.
- Summary: keep every key (schema 0.2 is settled), but `print(summary)` and the CLI
  default show a compact view (`ok`, `ship`, `deliver`, `issues`, top facts per
  panel). `--json full` prints everything.
- HTML class prefix `fm-` → `mf-`.

### Phase 6 — Show that it works

- The reader benchmark already listed as next in `HANDOFF.md` §6, with two added
  arms: *figure reply vs text-only reply of the same facts*, and *HTML with hover vs
  PNG*. This is the claim the README makes and has not measured.
- figure-bench gains a delivery check: the agent's final message contains the
  figure in the harness-appropriate form and at most 60 words of prose around it.
- README opens with one before/after: an agent's text-only answer beside the same
  answer as a mintfig reply.

## 5. Not doing

- **No new chart forms.** Facets and in-cell graphics are arguments on existing
  forms. The open scope question in `HANDOFF.md` §7 stays answered as "one form per
  question".
- **No node-link or architecture diagrams.** Structure is a real source of walls of
  text, but Mermaid already renders natively in most hosts and mintfig's advantage
  is quantitative honesty. `SKILL.md` gets one line pointing there.
- **No MCP server.** Settled in `HANDOFF.md` §7. Revisit only if the delivery check
  in Phase 6 shows figures still not reaching readers after Phase 1.
- **No animation, no toggles that hide data.** Side by side beats before/after in
  time ("eyes beat memory", Munzner).

## 6. Order and size

| Phase | Depends on | Size | Breaking? |
| :--- | :--- | :--- | :--- |
| 1 Last mile | — | Small | No (additive key, doc, one CLI command, terminal fixes) |
| 2 HTML | 1a | Medium | No |
| 3 Figure upgrades | — | Medium–large (3b largest) | 3a changes default renders |
| 4 Briefing | 1a, 3 | Small–medium | `brief()` signature widens |
| 5 API | — | Small, mechanical | Yes: clean break in 0.3.0, no shims |
| 6 Proof | 1–3 | Medium | No |

Phases 1 and 5 touch disjoint files and can run in parallel. Phase 3 changes
`_explain/` and should run alone.

## 7. Sources for the choices above

Tufte, *The Visual Display of Quantitative Information* (data-ink, lie factor, small
multiples, shrink principle) and *Beautiful Evidence* (sparklines, table-graphics,
integrating words and images) · Cleveland, *The Elements of Graphing Data* (common
scales, banking to 45°) · Shneiderman 1996 (overview first, details on demand) ·
Munzner, *Visualization Analysis and Design* (eyes beat memory; validate at each
level) · Few, *Information Dashboard Design* (density, bullet graphs) · Segel & Heer
2010 (annotated-chart narrative) · Franconeri et al. 2021, *The Science of Visual
Data Communication* (readers see what they are cued to compare).
