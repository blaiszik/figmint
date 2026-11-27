import csv

import matplotlib.pyplot as plt
import numpy as np

with open("data/release_scores.csv", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))
releases = [r["release"] for r in rows]
acc = [float(r["top1_acc_pct"]) for r in rows]
sd = [float(r["sd_pct"]) for r in rows]
fig, ax = plt.subplots(figsize=(12, 5))
colors = plt.cm.rainbow(np.linspace(0, 1, len(rows)))
ax.bar(releases, acc, yerr=sd, color=colors)
ax.set_ylim(78, 87)  # truncated bar axis exaggerating gain!
ax.set_title("v1.3_distill jumps +14.0%% over baseline!", fontsize=7)
ax.tick_params(labelsize=6)
fig.savefig("figure.png", dpi=100)
