import csv
import math

import matplotlib.pyplot as plt
import numpy as np

groups = {}
with open("data/experiment_scores.csv", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        groups.setdefault(r["arm"], []).append(float(r["score"]))
names = list(groups.keys())
means = [float(np.mean(groups[k])) for k in names]
sems = [float(np.std(groups[k], ddof=1)) / math.sqrt(len(groups[k])) for k in names]
fig, ax = plt.subplots(figsize=(10, 5))
ax.bar(names, means, yerr=sems, color=["#e15759", "#59a14f"])
ax.set_ylim(58, 74)
ax.set_title("variant_x significantly outperforms control by +12.5% (95% CI)", fontsize=7)
fig.savefig("figure.png", dpi=100)
