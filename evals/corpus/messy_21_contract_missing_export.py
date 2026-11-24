# target_journal: nature
"""Messy 21: Contract failure — defines make_plot() instead of build()/plate/fig."""

from __future__ import annotations

import numpy as np

import figmint as fm


def make_plot() -> fm.Plate:
    plate = fm.Plate(journal="nature", width="single", height_mm=64.0, layout=(1, 1))
    ax = plate["a"]
    x = np.linspace(0, 5, 100)
    ax.plot(x, np.exp(-0.4 * x), color=fm.get_palette("nature")[0])
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Fraction remaining")
    return plate
