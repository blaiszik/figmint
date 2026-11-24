# target_journal: nature
"""Messy 12: Figure-level title positioned outside top canvas bounds (clipping)."""

from __future__ import annotations

import numpy as np

import figmint as fm


def build() -> fm.Plate:
    rng = np.random.default_rng(212)
    plate = fm.Plate(journal="nature", width="single", height_mm=64.0, layout=(1, 1))
    ax = plate["a"]
    ax.imshow(rng.normal(0, 1, (12, 12)), cmap="viridis", aspect="auto")
    ax.set_xlabel("Time bin")
    ax.set_ylabel("Channel")
    plate.fig.text(0.50, 0.96, "Spatial Activity Matrix\nAcross Cortical Layers", ha="center", va="top", fontsize=6.5)
    return plate
