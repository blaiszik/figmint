# target_journal: nature
"""Messy 20: Oversized height_mm=260 exceeding Nature max_page_height_mm=247."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    plate = mint.Plate(
        journal="nature",
        width="double",
        height_mm=260.0,
        layout=[["a", "b"], ["c", "d"]],
        gap_mm=9.0,
    )
    x = np.linspace(0, 10, 80)
    colors = mint.get_palette("nature")
    for idx, key in enumerate(["a", "b", "c", "d"]):
        plate[key].plot(x, np.sin(x + idx * 0.7), color=colors[idx])
        plate[key].set_xlabel("Time (s)")
        plate[key].set_ylabel("Signal")
    plate.label_panels()
    return plate
