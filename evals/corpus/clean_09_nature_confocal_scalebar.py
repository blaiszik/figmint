# target_journal: nature
"""Clean control 09: Nature 89 mm synthetic confocal micrograph + scalebar."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    rng = np.random.default_rng(109)
    plate = mint.Plate(journal="nature", width="single", height_mm=72.0, layout=(1, 1))
    ax = plate["a"]

    yy, xx = np.mgrid[0:180, 0:220].astype(float)
    img = np.full_like(xx, 12.0)
    for _ in range(14):
        cx = rng.uniform(24, 196)
        cy = rng.uniform(24, 156)
        img += rng.uniform(70, 150) * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 10.5**2))
    img = rng.poisson(img).astype(float)

    im = ax.imshow(img, cmap="magma", vmin=5, vmax=190)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(True)
        sp.set_linewidth(0.5)
    mint.scalebar(ax, length=40.0, unit="µm", pixel_size=1.0, location="lower right", color="white", fontsize=6.0)
    cbar = plate.fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    mint.style_colorbar(cbar, label="Intensity (a.u.)", tick_pt=5.5)
    return plate
