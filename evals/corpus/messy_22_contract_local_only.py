# target_journal: science
"""Messy 22: Contract failure — assigns my_plate instead of plate/fig/build()."""

from __future__ import annotations

import numpy as np

import mintfig as mint

my_plate = mint.Plate(journal="science", width="double", height_mm=74.0, layout=(1, 1))
ax = my_plate["A"]
x = np.linspace(0, 10, 120)
ax.plot(x, np.cos(x) * np.exp(-0.12 * x), color=mint.get_palette("science")[0])
ax.set_xlabel("Time (ms)")
ax.set_ylabel("Voltage (mV)")
