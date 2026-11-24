# target_journal: nature
"""Messy 24: Compound 2x2 multi-panel mess — wrong size + rainbow + tiny text + overlap."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np


def build() -> plt.Figure:
    rng = np.random.default_rng(224)
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))

    t = np.linspace(0, 10, 80)
    axes[0, 0].plot(t, np.sin(t))
    axes[0, 0].set_xlabel("Time (s)")
    axes[0, 0].set_ylabel("Signal")

    mat = rng.normal(0, 1, (12, 12))
    axes[0, 1].imshow(mat, cmap="rainbow", aspect="auto")
    axes[0, 1].set_xlabel("Index")
    axes[0, 1].set_ylabel("Index")

    x = rng.normal(0, 1, 80)
    y = 0.7 * x + rng.normal(0, 0.4, 80)
    axes[1, 0].scatter(x, y, s=12)
    axes[1, 0].text(0.2, 0.8, "Cluster A", fontsize=3.8)
    axes[1, 0].text(0.22, 0.82, "Cluster B", fontsize=3.8)
    axes[1, 0].set_xlabel("PC1")
    axes[1, 0].set_ylabel("PC2")

    axes[1, 1].bar(["A", "B", "C"], [1.2, 2.4, 1.8])
    axes[1, 1].set_ylabel("Score")
    return fig
