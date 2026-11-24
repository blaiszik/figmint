# target_journal: nature
"""Messy 01: Stock plt.subplots() default 6.4x4.8 in scatter plot."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figmint as fm


def build() -> plt.Figure:
    fm.apply("nature")
    rng = np.random.default_rng(201)
    fig, ax = plt.subplots(figsize=(7.204724, 5.401575), layout="constrained")
    x = rng.normal(5.0, 1.2, 140)
    y = 0.78 * x + rng.normal(0.5, 0.65, 140)
    ax.scatter(x, y, alpha=0.7)
    ax.set_xlabel("RNA-seq expression (TPM)")
    ax.set_ylabel("Proteomics abundance (LFQ)")
    ax.set_title("Transcript-Protein Correlation")
    return fig
