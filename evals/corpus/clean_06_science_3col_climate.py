# target_journal: science
"""Clean control 06: Science 184 mm 3-column atmospheric plate (A, B, C)."""

from __future__ import annotations

import numpy as np

import figmint as fm


def build() -> fm.Plate:
    rng = np.random.default_rng(106)
    plate = fm.Plate(
        journal="science",
        width="full",
        height_mm=68.0,
        layout=[["A", "B", "C"]],
        gap_mm=9.5,
    )
    colors = fm.get_palette("science")

    yr = np.arange(1950, 2025)
    anom = 0.018 * (yr - 1950) + rng.normal(0.0, 0.12, len(yr))
    plate["A"].plot(yr, anom, color=colors[0], lw=0.85)
    plate["A"].set_xticks([1950, 1975, 2000, 2025])
    plate["A"].set_xlabel("Year")
    plate["A"].set_ylabel(r"$\Delta T$ (°C)")

    lat = np.linspace(-80, 80, 60)
    plate["B"].plot(lat, 0.9 + 1.4 * np.exp(-((lat - 75) / 25) ** 2), color=colors[1])
    plate["B"].set_xticks([-60, 0, 60])
    plate["B"].set_xlabel("Latitude (°)")
    plate["B"].set_ylabel("Warming (°C)")

    agents = [r"$\mathrm{CO}_2$", r"$\mathrm{CH}_4$", "Ozone", "Aerosol"]
    vals = [2.1, 0.55, 0.45, -1.0]
    plate["C"].barh(agents, vals, color=[colors[0], colors[0], colors[0], colors[1]], height=0.58)
    plate["C"].axvline(0.0, color="#222222", lw=0.5)
    plate["C"].set_xlabel(r"Forcing ($\mathrm{W\,m^{-2}}$)")

    plate.label_panels()
    return plate
