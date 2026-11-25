# target_journal: science
"""Messy 07: Science 2-col 2D phase field using banned cmap='hsv'."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    plate = mint.Plate(journal="science", width="double", height_mm=76.0, layout=(1, 1))
    ax = plate["A"]
    x = np.linspace(-3, 3, 80)
    y = np.linspace(-3, 3, 80)
    xx, yy = np.meshgrid(x, y)
    phase = np.arctan2(yy, xx)
    im = ax.imshow(phase, extent=[-3, 3, -3, 3], cmap="hsv", origin="lower")
    cbar = plate.fig.colorbar(im, ax=ax, fraction=0.045, pad=0.03)
    mint.style_colorbar(cbar, label="Phase (rad)")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    return plate
