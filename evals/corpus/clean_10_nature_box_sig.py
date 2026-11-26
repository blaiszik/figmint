# target_journal: nature
"""Clean control 10: Nature 89 mm strip+box with stacked sig_bracket (top-level plate)."""

from __future__ import annotations

import numpy as np

import mintfig as mint

rng = np.random.default_rng(110)
plate = mint.Plate(journal="nature", width="single", height_mm=68.0, layout=(1, 1))
ax = plate["a"]
colors = mint.pub.get_palette("nature")

groups = [
    rng.normal(1.0, 0.14, 24),
    rng.normal(0.72, 0.12, 24),
    rng.normal(0.41, 0.10, 24),
]
pos = np.arange(3, dtype=float)
bp = ax.boxplot(
    groups,
    positions=pos,
    widths=0.42,
    showfliers=False,
    patch_artist=True,
    medianprops={"color": "#111111", "linewidth": 0.85},
    boxprops={"linewidth": 0.55, "edgecolor": "#222222"},
    whiskerprops={"linewidth": 0.5, "color": "#222222"},
    capprops={"linewidth": 0.5, "color": "#222222"},
)
for idx, box in enumerate(bp["boxes"]):
    box.set_facecolor(colors[idx])
    box.set_alpha(0.25)
for idx, vals in enumerate(groups):
    ax.scatter(pos[idx] + rng.uniform(-0.12, 0.12, len(vals)), vals, color=colors[idx], s=8, alpha=0.75)

ax.set_xticks(pos)
ax.set_xticklabels(["Ctrl", "Low", "High"])
ax.set_ylim(0.0, 1.55)
ax.set_ylabel("Expression (norm.)")
mint.pub.sig_bracket(ax, 0, 1, p=0.0042, lw=0.55, fontsize=5.5)
mint.pub.sig_bracket(ax, 0, 2, p=0.00003, lw=0.55, fontsize=5.5)
