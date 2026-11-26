# target_journal: nature
"""Messy 05: Nature plate volcano scatter using banned cmap='jet'."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    rng = np.random.default_rng(205)
    plate = mint.Plate(journal="nature", width="single", height_mm=66.0, layout=(1, 1))
    ax = plate["a"]
    fc = rng.normal(0.0, 1.4, 300)
    score = np.abs(fc) * 1.5 + rng.exponential(0.6, 300)
    sc = ax.scatter(fc, score, c=score, cmap="jet", s=10, edgecolors="none")
    cbar = plate.fig.colorbar(sc, ax=ax, fraction=0.05, pad=0.03)
    mint.pub.style_colorbar(cbar, label="Significance")
    ax.set_xlabel(r"$\log_2$ fold change")
    ax.set_ylabel(r"$-\log_{10}(p)$")
    return plate
