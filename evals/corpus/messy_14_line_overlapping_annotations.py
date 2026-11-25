# target_journal: nature
"""Messy 14: Line kinetics with two overlapping peak annotations."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    plate = mint.Plate(journal="nature", width="single", height_mm=66.0, layout=(1, 1))
    ax = plate["a"]
    colors = mint.get_palette("nature")
    t = np.linspace(0, 24, 150)
    y1 = 6.0 * (1 - np.exp(-t / 1.5)) * np.exp(-t / 10.0)
    y2 = 4.2 * (1 - np.exp(-t / 2.0)) * np.exp(-t / 12.0)
    ax.plot(t, y1, color=colors[0], label="WT")
    ax.plot(t, y2, color=colors[3], label="KO")
    ax.text(5.0, 4.4, "WT peak", fontsize=6.0, color=colors[0])
    ax.text(5.1, 4.42, "KO peak", fontsize=6.0, color=colors[3])
    ax.set_ylim(0, 6.2)
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("Signal (a.u.)")
    return plate
