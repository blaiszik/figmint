# target_journal: nature
"""Clean control 01: Nature 89 mm single-column pharmacological dose-response."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    rng = np.random.default_rng(101)
    plate = mint.Plate(journal="nature", width="single", height_mm=64.0, layout=(1, 1))
    ax = plate["a"]
    colors = mint.pub.get_palette("nature")

    conc = np.geomspace(1e-3, 1e2, 180)
    pts = np.geomspace(1e-3, 1e2, 8)
    for idx, (label, ic50) in enumerate([("Lead A", 0.025), ("Lead B", 0.45), ("Control", 4.0)]):
        y = 6.0 + 92.0 / (1.0 + (conc / ic50) ** 1.15)
        ci = 3.0 + 2.0 * np.exp(-0.5 * np.log10(conc / ic50) ** 2)
        ax.fill_between(conc, y - ci, y + ci, color=colors[idx], alpha=0.16, linewidth=0.0)
        ax.plot(conc, y, color=colors[idx], linewidth=1.0, label=label)
        y_pts = 6.0 + 92.0 / (1.0 + (pts / ic50) ** 1.15) + rng.normal(0.0, 2.5, size=len(pts))
        ax.scatter(pts, y_pts, color=colors[idx], s=10, edgecolors="white", linewidths=0.4, zorder=4)

    ax.set_xscale("log")
    ax.set_xlim(7e-4, 1.4e2)
    ax.set_ylim(0, 108)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel(r"Concentration ($\mu\mathrm{M}$)")
    ax.set_ylabel("Activity (% vehicle)")
    mint.pub.direct_labels(ax, pad_pt=3.0, min_sep_pt=8.0, expand_xlim=0.34)
    ax.spines["bottom"].set_bounds(7e-4, 1.4e2)
    return plate
