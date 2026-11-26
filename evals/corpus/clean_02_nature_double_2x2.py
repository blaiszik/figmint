# target_journal: nature
"""Clean control 02: Nature 183 mm double-column 2x2 multi-panel plate."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    rng = np.random.default_rng(102)
    plate = mint.Plate(
        journal="nature",
        width="double",
        height_mm=112.0,
        layout=[["a", "b"], ["c", "d"]],
        gap_mm=(10.0, 9.5),
    )
    colors = mint.pub.get_palette("nature")

    # a: time series
    t = np.linspace(0, 12, 120)
    y1 = 1.0 - np.exp(-t / 2.5)
    y2 = 0.65 * (1.0 - np.exp(-t / 4.0))
    plate["a"].plot(t, y1, color=colors[0], label="WT")
    plate["a"].plot(t, y2, color=colors[3], label="Mutant")
    plate["a"].set_xlabel("Time (h)")
    plate["a"].set_ylabel("Response (a.u.)")
    plate["a"].legend(loc="lower right", frameon=False)

    # b: scatter correlation
    x = rng.normal(0.0, 1.0, 120)
    y = 0.82 * x + rng.normal(0.0, 0.45, 120)
    plate["b"].scatter(x, y, s=9, color=colors[1], alpha=0.7, edgecolors="none")
    plate["b"].set_xlabel("Replicate 1 (log2)")
    plate["b"].set_ylabel("Replicate 2 (log2)")

    # c: grouped bar
    cats = ["Ctrl", "Drug A", "Drug B", "Combo"]
    vals = [1.0, 0.72, 0.54, 0.31]
    errs = [0.08, 0.07, 0.06, 0.05]
    plate["c"].bar(cats, vals, yerr=errs, color=colors[:4], alpha=0.85, capsize=2.0, error_kw={"lw": 0.55})
    plate["c"].set_ylabel("Relative viability")

    # d: distribution histogram
    d1 = rng.normal(2.2, 0.6, 400)
    d2 = rng.normal(3.6, 0.7, 400)
    plate["d"].hist(d1, bins=22, alpha=0.55, color=colors[2], label="Baseline")
    plate["d"].hist(d2, bins=22, alpha=0.55, color=colors[0], label="Treated")
    plate["d"].set_xlabel("Fluorescence (log10)")
    plate["d"].set_ylabel("Cell count")
    plate["d"].legend(loc="upper right", frameon=False)

    plate.label_panels()
    return plate
