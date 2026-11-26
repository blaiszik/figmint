# target_journal: science
"""Clean control 05: Science 120 mm 2-column volcano plot."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    rng = np.random.default_rng(105)
    plate = mint.Plate(journal="science", width="double", height_mm=76.0, layout=(1, 1))
    ax = plate["A"]
    colors = mint.pub.get_palette("science")

    fc = rng.normal(0.0, 1.3, 600)
    neglogp = np.abs(fc) * rng.uniform(0.6, 2.2, 600) + rng.exponential(0.5, 600)
    up = (fc > 1.2) & (neglogp > 2.0)
    dn = (fc < -1.2) & (neglogp > 2.0)
    ns = ~(up | dn)

    ax.scatter(fc[ns], neglogp[ns], s=6, color="#9CA3AF", alpha=0.45, edgecolors="none")
    ax.scatter(fc[up], neglogp[up], s=8, color=colors[1], alpha=0.8, edgecolors="none", label="Up")
    ax.scatter(fc[dn], neglogp[dn], s=8, color=colors[0], alpha=0.8, edgecolors="none", label="Down")
    ax.axvline(-1.2, color="#6B7280", ls="--", lw=0.45)
    ax.axvline(1.2, color="#6B7280", ls="--", lw=0.45)
    ax.axhline(2.0, color="#6B7280", ls="--", lw=0.45)
    ax.set_xlabel(r"$\log_2$ fold change")
    ax.set_ylabel(r"$-\log_{10}(p)$")
    ax.legend(loc="upper left", frameon=False)
    return plate
