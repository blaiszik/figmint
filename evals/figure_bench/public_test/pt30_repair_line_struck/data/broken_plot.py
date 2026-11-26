"""Draft throughput scaling chart (has line-struck, malformed, and clipped text)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "pt30_broken.png"

series: dict[str, tuple[list[int], list[float]]] = {}
with open(DATA_DIR / "throughput.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        xs, ys = series.setdefault(row["release"], ([], []))
        xs.append(int(row["concurrency"]))
        ys.append(float(row["req_per_sec"]))

fig, ax = plt.subplots(figsize=(7, 4.4), dpi=100)
colors = {"v1.0": "#64748b", "v1.1": "#d97706", "v2.0": "#2563eb"}
for rel, (xs, ys) in series.items():
    ax.plot(xs, ys, marker="o", linewidth=2.2, color=colors[rel], label=rel)

ax.text(32, 4490, "v2.0 (+48%% at c=64)", fontsize=11, color=colors["v2.0"], ha="center", va="center")
ax.text(64, 2960, "v1.1 (-19% at c=128)", fontsize=11, color=colors["v1.1"], ha="center", va="center")
ax.text(129, 4150, "v2.0 release throughput end", fontsize=11, color=colors["v2.0"], va="center", clip_on=False)

ax.set_xlim(0, 130)
ax.set_ylim(0, 5400)
ax.set_xlabel("Concurrency (workers)", fontsize=11)
ax.set_ylabel("Throughput (req/s)", fontsize=11)
ax.set_title("v2.0 peaks at 4,820 req/s (+48%% over v1.0)", fontsize=12)
fig.savefig(OUT_PATH, dpi=100)
