# target_journal: nature
"""Messy 02: Oversized figsize=(7.204724, 4.322835) enzyme kinetics line plot."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figmint as fm


def build() -> plt.Figure:
    fm.apply("nature")
    fig, ax = plt.subplots(figsize=(7.204724, 4.322835), layout="constrained")
    s = np.linspace(0, 50, 120)
    ax.plot(s, 1.2 * s / (4.5 + s), label="Wild-type")
    ax.plot(s, 0.8 * s / (9.0 + s), label="Variant R142A")
    ax.set_xlabel("Substrate (uM)")
    ax.set_ylabel("Initial velocity (uM/s)")
    ax.legend(loc="lower right")
    return fig
