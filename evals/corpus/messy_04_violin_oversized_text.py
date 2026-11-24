# target_journal: nature
"""Messy 04: Wrong figsize=(8, 5) + oversized 15 pt title on violin plot."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np


def build() -> plt.Figure:
    rng = np.random.default_rng(204)
    fig, ax = plt.subplots(figsize=(8, 5))
    data = [rng.normal(m, 0.35, 80) for m in (1.2, 1.8, 2.5)]
    ax.violinplot(data, showmedians=True)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(["G1", "S", "G2/M"])
    ax.set_ylabel("Cell cycle score")
    ax.set_title("Single-Cell Cycle Score", fontsize=15)
    return fig
