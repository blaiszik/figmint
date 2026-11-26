# target_journal: nature
"""Messy 19: Spectroscopy plot with 0.1 pt hairline strokes below 0.25 pt print min."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    plate = mint.Plate(journal="nature", width="single", height_mm=64.0, layout=(1, 1))
    ax = plate["a"]
    colors = mint.pub.get_palette("nature")
    freq = np.linspace(100, 900, 240)
    spec = np.exp(-0.5 * ((freq - 420) / 35) ** 2) + 0.6 * np.exp(-0.5 * ((freq - 650) / 45) ** 2)
    ax.plot(freq, spec, color=colors[0], linewidth=0.1)
    ax.axhline(0.5, color="#666666", linestyle="--", lw=0.1)
    ax.set_xlabel("Wavenumber (cm-1)")
    ax.set_ylabel("Intensity (norm.)")
    return plate
