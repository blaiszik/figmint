# target_journal: nature
"""Messy 10: ROC curve with tiny 3.8 pt AUC callout text."""

from __future__ import annotations

import numpy as np

import figmint as fm


def build() -> fm.Plate:
    plate = fm.Plate(journal="nature", width="single", height_mm=66.0, layout=(1, 1))
    ax = plate["a"]
    colors = fm.get_palette("nature")
    fpr = np.linspace(0, 1, 120)
    ax.plot([0, 1], [0, 1], ls="--", color="#9CA3AF", lw=0.5)
    ax.plot(fpr, fpr**0.25, color=colors[0], label="Classifier")
    ax.text(0.55, 0.25, "AUC = 0.91", fontsize=3.8, color=colors[0])
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.legend(loc="lower right", frameon=False)
    return plate
