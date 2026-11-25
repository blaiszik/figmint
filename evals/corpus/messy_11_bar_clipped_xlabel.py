# target_journal: nature
"""Messy 11: Unconstrained figure where long bottom label clips off canvas."""

from __future__ import annotations

import matplotlib.pyplot as plt

import mintfig as mint


def build() -> plt.Figure:
    with mint.use("nature"):
        fig, ax = plt.subplots(figsize=(mint.mm_to_in(89.0), mint.mm_to_in(58.0)))
        fig.subplots_adjust(bottom=0.05, left=0.12, right=0.96, top=0.92)
        cats = ["Control", "Inhibitor A", "Inhibitor B", "Combinatorial"]
        vals = [1.0, 0.68, 0.51, 0.28]
        ax.bar(cats, vals, color=mint.get_palette("nature")[:4])
        ax.set_xlabel("Pharmacological perturbation condition across replicate cohorts")
        ax.set_ylabel("Normalized pathway activity")
    return fig
