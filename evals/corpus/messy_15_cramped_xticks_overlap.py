# target_journal: science
"""Messy 15: Narrow 55 mm Science 1-col bar plot with cramped colliding x-ticks."""

from __future__ import annotations

import mintfig as mint


def build() -> mint.Plate:
    plate = mint.Plate(journal="science", width="single", height_mm=56.0, layout=(1, 1))
    ax = plate["A"]
    colors = mint.get_palette("science")
    labels = ["Condition_01", "Condition_02", "Condition_03", "Condition_04", "Condition_05", "Condition_06"]
    vals = [1.2, 1.8, 1.5, 2.3, 1.9, 2.6]
    ax.bar(range(len(labels)), vals, color=colors[0], alpha=0.85)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Response")
    return plate
