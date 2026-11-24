# target_journal: nature
"""Messy 17: Script forces serif Times fontfamily on axis labels."""

from __future__ import annotations

import numpy as np

import figmint as fm


def build() -> fm.Plate:
    plate = fm.Plate(journal="nature", width="single", height_mm=64.0, layout=(1, 1))
    ax = plate["a"]
    x = np.linspace(0, 8, 100)
    ax.plot(x, np.exp(-0.3 * x) * np.cos(2 * x), color=fm.get_palette("nature")[0])
    ax.set_xlabel("Delay (ps)", fontfamily="serif")
    ax.set_ylabel("Reflectivity (a.u.)", fontfamily="serif")
    return plate
