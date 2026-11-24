# target_journal: science
"""Messy 03: Wrong figsize=(7, 5) for Science cytokine bar chart."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np


def build() -> plt.Figure:
    fig, ax = plt.subplots(figsize=(7, 5))
    cytokines = ["IL-6", "TNFa", "IFNg", "IL-1b"]
    vals = np.array([4.2, 3.1, 5.6, 2.4])
    errs = np.array([0.4, 0.3, 0.5, 0.25])
    ax.bar(cytokines, vals, yerr=errs, capsize=3)
    ax.set_ylabel("Fold induction")
    ax.set_xlabel("Cytokine")
    return fig
