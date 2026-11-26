# target_journal: nature
"""Messy 06: Nature plate correlation heatmap using banned cmap='rainbow'."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    rng = np.random.default_rng(206)
    plate = mint.Plate(journal="nature", width="single", height_mm=70.0, layout=(1, 1))
    ax = plate["a"]
    mat = rng.uniform(-1, 1, (10, 10))
    mat = 0.5 * (mat + mat.T)
    np.fill_diagonal(mat, 1.0)
    im = ax.imshow(mat, cmap="rainbow", vmin=-1, vmax=1)
    cbar = plate.fig.colorbar(im, ax=ax, fraction=0.048, pad=0.03)
    mint.pub.style_colorbar(cbar, label="Pearson r")
    ax.set_xlabel("Sample")
    ax.set_ylabel("Sample")
    return plate
