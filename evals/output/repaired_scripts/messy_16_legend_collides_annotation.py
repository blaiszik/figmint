# target_journal: nature
"""Messy 16: Legend collides directly with upper-left annotation text."""

from __future__ import annotations

import numpy as np

import figmint as fm


def build() -> fm.Plate:
    plate = fm.Plate(journal="nature", width="single", height_mm=66.0, layout=(1, 1))
    ax = plate["a"]
    colors = fm.get_palette("nature")
    x = np.linspace(0, 10, 100)
    ax.plot(x, 0.35 * x + 0.4, color=colors[0], label="Treatment A")
    ax.plot(x, 0.22 * x + 0.2, color=colors[1], label="Treatment B")
    ax.legend(loc="lower right", frameon=False)
    ax.text(0.6, 3.65, "Linear regime (R2 = 0.99)", fontsize=6.0, color="#222222")
    ax.set_ylim(0, 4.2)
    ax.set_xlabel("Dose (mM)")
    ax.set_ylabel("Yield (mM)")
    return plate
