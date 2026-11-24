# target_journal: science
"""Clean control 04: Science 55 mm 1-column absorption spectrum."""

from __future__ import annotations

import numpy as np

import figmint as fm


def build(journal: str = "science") -> fm.Plate:
    plate = fm.Plate(journal=journal, width="single", height_mm=50.0, layout=(1, 1))
    ax = plate["A"]
    colors = fm.get_palette("science")

    wl = np.linspace(380, 720, 220)
    s1 = 0.92 * np.exp(-0.5 * ((wl - 485) / 26) ** 2) + 0.35 * np.exp(-0.5 * ((wl - 610) / 30) ** 2)
    s2 = 0.78 * np.exp(-0.5 * ((wl - 535) / 28) ** 2)
    ax.plot(wl, s1, color=colors[0], label="Dark")
    ax.plot(wl, s2, color=colors[1], label="Light")
    ax.set_xlim(380, 720)
    ax.set_ylim(0, 1.1)
    ax.set_xticks([400, 550, 700])
    ax.set_yticks([0.0, 0.5, 1.0])
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Absorbance")
    ax.legend(loc="upper right", frameon=False)
    return plate
