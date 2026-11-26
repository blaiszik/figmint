# target_journal: science
"""Messy 09: Science 2-col residual plot with 4.2 pt tick labels (< 6 pt min)."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    rng = np.random.default_rng(209)
    plate = mint.Plate(journal="science", width="double", height_mm=72.0, layout=(1, 1))
    ax = plate["A"]
    colors = mint.pub.get_palette("science")
    fitted = np.linspace(1.0, 10.0, 90)
    resid = rng.normal(0.0, 0.45, 90)
    ax.axhline(0.0, ls="--", color="#6B7280", lw=0.5)
    ax.scatter(fitted, resid, s=11, color=colors[0], alpha=0.75, edgecolors="none")
    ax.tick_params(labelsize=4.2)
    ax.set_xlabel("Fitted value")
    ax.set_ylabel("Residual")
    return plate
