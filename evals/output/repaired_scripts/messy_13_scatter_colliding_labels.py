# target_journal: nature
"""Messy 13: Scatter plot with severe colliding gene annotations."""

from __future__ import annotations

import numpy as np

import figmint as fm


def build() -> fm.Plate:
    rng = np.random.default_rng(213)
    plate = fm.Plate(journal="nature", width="single", height_mm=68.0, layout=(1, 1))
    ax = plate["a"]
    colors = fm.get_palette("nature")
    x = rng.normal(0.0, 1.2, 150)
    y = rng.normal(0.0, 1.2, 150)
    ax.scatter(x, y, s=9, color=colors[1], alpha=0.65, edgecolors="none")
    ax.text(1.5, 1.8, "STAT3", fontsize=6.0, fontweight="bold", color=colors[0])
    ax.text(1.52, 1.07, "SOCS3", fontsize=6.0, fontweight="bold", color=colors[3])
    ax.set_xlabel("Component 1")
    ax.set_ylabel("Component 2")
    return plate
