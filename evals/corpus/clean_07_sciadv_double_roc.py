# target_journal: science_advances
"""Clean control 07: Science Advances 175 mm double-column ROC + PR curves."""

from __future__ import annotations

import numpy as np

import figmint as fm


def build() -> fm.Plate:
    plate = fm.Plate(
        journal="science_advances",
        width="double",
        height_mm=74.0,
        layout=[["A", "B"]],
        gap_mm=10.0,
    )
    colors = fm.get_palette("science")
    x = np.linspace(0, 1, 150)

    # A: ROC
    plate["A"].plot([0, 1], [0, 1], ls="--", color="#9CA3AF", lw=0.5)
    plate["A"].plot(x, x**0.22, color=colors[0], label="Model (0.94)")
    plate["A"].plot(x, x**0.48, color=colors[1], label="Baseline (0.78)")
    plate["A"].set_xlabel("False positive rate")
    plate["A"].set_ylabel("True positive rate")
    plate["A"].legend(loc="lower right", frameon=False)

    # B: Precision-Recall
    plate["B"].plot(x, 0.96 - 0.35 * x**2.2, color=colors[0], label="Model")
    plate["B"].plot(x, 0.85 - 0.55 * x**1.4, color=colors[1], label="Baseline")
    plate["B"].set_ylim(0, 1.05)
    plate["B"].set_xlabel("Recall")
    plate["B"].set_ylabel("Precision")
    plate["B"].legend(loc="lower left", frameon=False)

    plate.label_panels()
    return plate
