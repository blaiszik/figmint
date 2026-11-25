# target_journal: nature
"""Messy 21: Contract failure — defines make_plot() instead of build()/plate/fig."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def make_plot() -> mint.Plate:
    plate = mint.Plate(journal="nature", width="single", height_mm=64.0, layout=(1, 1))
    ax = plate["a"]
    x = np.linspace(0, 5, 100)
    ax.plot(x, np.exp(-0.4 * x), color=mint.get_palette("nature")[0])
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Fraction remaining")
    return plate
