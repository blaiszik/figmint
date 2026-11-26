"""Draft regional latency boxplot (wrong median claim, tiny fonts, unlabelled y-axis)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "h14_broken.png"

regions = ["us-east", "us-west", "eu-central", "ap-northeast"]
buckets: dict[str, list[float]] = {r: [] for r in regions}
with open(DATA_DIR / "latencies.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        buckets[row["region"]].append(float(row["latency_ms"]))

fig, ax = plt.subplots(figsize=(14, 5), dpi=100)
ax.boxplot([buckets[r] for r in regions], tick_labels=regions)
ax.tick_params(labelsize=9)
ax.set_title("ap-northeast median latency (ms) reaches 312", fontsize=11)
fig.savefig(OUT_PATH, dpi=100)
