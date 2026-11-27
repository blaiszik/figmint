"""Draft confusion matrix heatmap (has colormap, text, and claim bugs)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "pt29_broken.png"

classes = ["billing", "auth", "infra", "search", "export"]
idx = {c: i for i, c in enumerate(classes)}
mat = np.zeros((len(classes), len(classes)), dtype=int)
with open(DATA_DIR / "confusion.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        mat[idx[row["true_label"]], idx[row["pred_label"]]] = int(row["count"])

fig, ax = plt.subplots(figsize=(13, 9), dpi=100)
im = ax.imshow(mat, cmap="jet")
fig.colorbar(im, ax=ax, label="Tickets")
ax.set_xticks(range(len(classes)))
ax.set_yticks(range(len(classes)))
ax.set_xticklabels(classes, fontsize=8)
ax.set_yticklabels(classes, fontsize=8)
ax.set_xlabel("Predicted queue", fontsize=8)
ax.set_ylabel("True queue", fontsize=8)

for i in range(len(classes)):
    for j in range(len(classes)):
        ax.text(j, i, f"{mat[i, j]}", ha="center", va="center", fontsize=8, color="white")
        ax.text(j, i + 0.04, f"({mat[i, j] / 2:.0f}%)", ha="center", va="center", fontsize=8, color="yellow")

ax.set_title("Ticket router achieves 96.4% overall accuracy", fontsize=12)
fig.savefig(OUT_PATH, dpi=100)
