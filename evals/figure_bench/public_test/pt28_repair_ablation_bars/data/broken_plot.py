"""Draft ablation plot (has visual & claim defects to repair)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "pt28_broken.png"

grouped: dict[str, list[float]] = {}
with open(DATA_DIR / "ablation.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        grouped.setdefault(row["variant"], []).append(float(row["f1_score"]))

names = list(grouped.keys())
means = [float(np.mean(grouped[k])) for k in names]
sds = [float(np.std(grouped[k], ddof=1)) for k in names]

fig, ax = plt.subplots(figsize=(14, 5), dpi=100)
x = np.arange(len(names))
ax.bar(x, means, yerr=sds, capsize=4, color="#3b82f6")
ax.set_xticks(x)
ax.set_xticklabels(names, fontsize=10)
ax.tick_params(axis="y", labelsize=10)
ax.set_ylabel("F1 score", fontsize=10)
ax.set_ylim(0.65, 0.85)
ax.set_title("Query rewrite adds 14.8 points to F1 score", fontsize=12)
fig.savefig(OUT_PATH, dpi=100)
