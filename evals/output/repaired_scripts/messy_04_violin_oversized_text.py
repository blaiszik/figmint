# target_journal: nature
"""Messy 04: Wrong figsize=(4.724409, 2.952756) + oversized 15 pt title on violin plot."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figmint as fm


def build() -> plt.Figure:
    fm.apply("nature")
    rng = np.random.default_rng(204)
    fig, ax = plt.subplots(figsize=(4.724409, 2.952756), layout="constrained")
    data = [rng.normal(m, 0.35, 80) for m in (1.2, 1.8, 2.5)]
    ax.violinplot(data, showmedians=True)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(["G1", "S", "G2/M"])
    ax.set_ylabel("Cell cycle score")
    ax.set_title("Single-Cell Cycle Score", fontsize=6.5)
    return fig
