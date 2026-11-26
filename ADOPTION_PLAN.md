# Adoption plan: from "nice tool" to "used by thousands"

Written 2026-11-25. Current estimate: 4/10 likely to reach thousands of users.
The goal is to remove the reasons a person or an agent would choose plain
Matplotlib instead, and to give everyone else a concrete reason to switch.

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

1. `mint.style()`: one call that gives any Matplotlib figure the house look at
   chat width. It's a thin wrapper over the existing `mint.pub.use`.
2. `mint.explain(takeaway, fig_or_ax)`: accept an existing Figure/Axes as a panel,
   and run the layout audit, `ship`, `deliver`, and HTML/terminal output on it.
3. **Facts from artists:** read the data back out of `Line2D`, `BarContainer`,
   `PathCollection` and error bars, then compute the same facts (highest, ratios,
   crossings, interval overlap). Then `claim_number_mismatch` works on any plot.
   This is the "linked to facts" promise extended to code nobody rewrote.

Done when: a gallery of five ugly agent-written Matplotlib scripts each becomes
a shippable figure with facts by adding 1–2 lines.

## C. Prove it, against Matplotlib rather than against text

The README compares mintfig only to a text answer. The objection people actually
raise is "my agent already makes plots."

1. **A Matplotlib arm in figure-bench (cheap, do first).** Run the same 15 tasks
   with an agent told to use plain Matplotlib. Score whether the takeaway's number
   is right, text size at display width, audit defects (overlap, clipping),
   unlabelled intervals, and time. The harness already exists.
2. **A three-column README opener:** agent text | agent Matplotlib | mintfig, on a
   genuinely complex result (multi-panel, uncertainty, a control).
3. **Reader benchmark** (HANDOFF §6, item 1): factual accuracy and time for VLM
   readers first, then 20–50 people, comparing text, agent Matplotlib and mintfig.

## D. Distribution

- Settle the PyPI name. HANDOFF §2 says `mintfig` is taken but also lists it as
  free, while the README says `pip install mintfig`.
- Package the skill as a Claude Code plugin and submit it to the plugin, skill
  and Codex/Cursor directories. This is packaging only; CLI + SKILL.md stays the
  interface, not MCP (a settled decision).
- **Trigger eval:** 30 realistic prompts that never mention mintfig ("summarize
  the benchmark run", "how did the ablation go"). Measure how often the agent uses
  the skill, and iterate on the description until it triggers reliably.
- `mintfig skill --print` should also print the reference files.
- Notebook, Quarto and marimo examples in the gallery.

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

| Phase | Work | Expected effect |
| :--- | :--- | :--- |
| 1 (~1 week) | C1 Matplotlib arm, C2 README opener, A relax rules, settle the name | The objection gets a measured answer |
| 2 | B bring-your-own Matplotlib | Adopting costs one line |
| 3 | D plugin and directories, trigger eval, C3 reader study | People can find it, and it triggers on its own |
| 4 | E domain forms, F 1.0 | Depth in science, and trust |

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
