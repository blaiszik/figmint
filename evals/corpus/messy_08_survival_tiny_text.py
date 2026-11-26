# target_journal: nature
"""Messy 08: Kaplan-Meier survival curve with tiny 3.5 pt annotations."""

from __future__ import annotations

import numpy as np

import mintfig as mint


def build() -> mint.Plate:
    plate = mint.Plate(journal="nature", width="single", height_mm=66.0, layout=(1, 1))
    ax = plate["a"]
    colors = mint.pub.get_palette("nature")
    t = np.linspace(0, 60, 60)
    s_hi = np.exp(-t / 52.0)
    s_lo = np.exp(-t / 24.0)
    ax.step(t, s_hi, where="post", color=colors[0], label="Treated")
    ax.step(t, s_lo, where="post", color=colors[3], label="Control")
    ax.text(32, 0.82, "HR = 0.44", fontsize=3.5, color=colors[0])
    ax.text(32, 0.72, "log-rank p = 0.002", fontsize=3.5, color="#333333")
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Follow-up (months)")
    ax.set_ylabel("Survival probability")
    ax.legend(loc="lower left", frameon=False)
    return plate
