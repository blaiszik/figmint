# target_journal: science
"""Messy 25: Compound Science mess — wrong figsize + jet + colliding labels + clipped suptitle."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np


def build() -> plt.Figure:
    rng = np.random.default_rng(225)
    fig, ax = plt.subplots(figsize=(8, 5))
    x = rng.normal(0, 1.1, 180)
    y = rng.normal(0, 1.1, 180)
    c = np.hypot(x, y)
    sc = ax.scatter(x, y, c=c, cmap="jet", s=16)
    fig.colorbar(sc, ax=ax, label="Radius")
    ax.text(0.5, 1.2, "State Alpha", fontsize=6.5)
    ax.text(0.52, 1.22, "State Beta", fontsize=6.5)
    fig.text(0.5, 1.03, "High-Dimensional State Space Projection", ha="center", va="bottom", fontsize=7.0)
    ax.set_xlabel("Dim 1")
    ax.set_ylabel("Dim 2")
    return fig
