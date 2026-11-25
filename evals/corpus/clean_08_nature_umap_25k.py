# target_journal: nature
"""Clean control 08: Nature 89 mm 25,000-point UMAP scatter (hybrid raster)."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    rng = np.random.default_rng(108)
    plate = mint.Plate(journal="nature", width="single", height_mm=72.0, layout=(1, 1))
    ax = plate["a"]
    colors = mint.get_palette("nature")

    centers = [(-3.0, 2.5), (3.0, 2.2), (0.0, -2.5), (-3.2, -2.6)]
    names = ["Cluster 1", "Cluster 2", "Cluster 3", "Cluster 4"]
    xs, ys, cs = [], [], []
    for i, (cx, cy) in enumerate(centers):
        n = 6250
        xs.append(rng.normal(cx, 0.95, n))
        ys.append(rng.normal(cy, 0.75, n))
        cs.append(np.full(n, i))

    x = np.concatenate(xs)
    y = np.concatenate(ys)
    c = np.concatenate(cs)
    ax.scatter(x, y, c=[colors[i] for i in c], s=0.9, alpha=0.45, edgecolors="none", linewidths=0.0)

    offsets = [(-3.0, 5.2), (3.0, 4.9), (0.0, -5.2), (-3.5, -5.2)]
    for i, (name, (lx, ly)) in enumerate(zip(names, offsets, strict=True)):
        ax.text(lx, ly, name, fontsize=5.8, fontweight="bold", color=colors[i], ha="center", va="center")

    ax.set_xlim(-6.8, 6.8)
    ax.set_ylim(-6.4, 6.4)
    ax.set_xlabel("UMAP 1")
    ax.set_ylabel("UMAP 2")
    return plate
