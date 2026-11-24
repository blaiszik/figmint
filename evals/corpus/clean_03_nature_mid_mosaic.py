# target_journal: nature
"""Clean control 03: Nature 120 mm 1.5-column mosaic plate."""

from __future__ import annotations

import numpy as np

import figmint as fm


def build() -> fm.Plate:
    rng = np.random.default_rng(103)
    plate = fm.Plate(
        journal="nature",
        width="mid",
        height_mm=82.0,
        layout=[["a", "b"], ["a", "c"]],
        gap_mm=(9.0, 8.5),
        width_ratios=[1.2, 1.0],
    )
    colors = fm.get_palette("nature")

    # a: heatmap
    mat = rng.normal(0.0, 1.0, (14, 14))
    mat = 0.5 * (mat + mat.T)
    np.fill_diagonal(mat, 3.0)
    im = plate["a"].imshow(mat, cmap="viridis", aspect="auto")
    plate["a"].set_xlabel("Gene module")
    plate["a"].set_ylabel("Gene module")
    cbar = plate.fig.colorbar(im, ax=plate["a"], fraction=0.055, pad=0.03)
    fm.style_colorbar(cbar, label="Correlation")

    # b: line trace
    x = np.linspace(0, 10, 80)
    plate["b"].plot(x, np.sin(x) * np.exp(-0.15 * x), color=colors[0])
    plate["b"].set_xlabel("Lag (s)")
    plate["b"].set_ylabel("Autocorr.")

    # c: decay curve
    plate["c"].plot(x, np.exp(-0.35 * x), color=colors[3])
    plate["c"].set_xlabel("Distance (mm)")
    plate["c"].set_ylabel("Signal")

    plate.label_panels()
    return plate
