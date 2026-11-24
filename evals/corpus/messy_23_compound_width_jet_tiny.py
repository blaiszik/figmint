# target_journal: nature
"""Messy 23: Compound 3-bug script — wrong figsize + cmap='jet' + 3.5 pt label."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np


def build() -> plt.Figure:
    fig, ax = plt.subplots(figsize=(9, 6))
    x = np.linspace(-2, 2, 70)
    y = np.linspace(-2, 2, 70)
    xx, yy = np.meshgrid(x, y)
    field = np.exp(-(xx**2 + yy**2)) * np.cos(2.5 * xx)
    im = ax.imshow(field, extent=[-2, 2, -2, 2], cmap="jet", origin="lower")
    fig.colorbar(im, ax=ax, label="Potential (mV)")
    ax.text(-1.8, 1.65, "Peak hotspot", fontsize=3.5, color="white")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    return fig
