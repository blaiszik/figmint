# target_journal: science
"""Messy 18: Raw matplotlib script sets DejaVu Serif family + wrong Type 3 fonttype."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figmint as fm


def build() -> plt.Figure:
    fm.apply("science")
    fig, ax = plt.subplots(figsize=(120.0 / 25.4, 76.0 / 25.4), layout="constrained")
    x = np.linspace(0, 6, 120)
    ax.plot(x, np.sin(x), color="#3B4992")
    ax.set_xlabel("Phase (rad)")
    ax.set_ylabel("Amplitude")
    return fig
