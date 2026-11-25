# target_journal: nature
"""Messy 12: Figure-level title positioned outside top canvas bounds (clipping)."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    rng = np.random.default_rng(212)
    plate = mint.Plate(journal="nature", width="single", height_mm=64.0, layout=(1, 1))
    ax = plate["a"]
    ax.imshow(rng.normal(0, 1, (12, 12)), cmap="viridis", aspect="auto")
    ax.set_xlabel("Time bin")
    ax.set_ylabel("Channel")
    plate.fig.text(0.5, 1.03, "Spatial Activity Matrix Across Cortical Layers", ha="center", va="bottom", fontsize=6.5)
    return plate
