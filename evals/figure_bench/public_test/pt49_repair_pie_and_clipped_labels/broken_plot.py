import csv

import matplotlib.pyplot as plt

with open("data/error_taxonomy.csv", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))
counts = [float(r["count"]) for r in rows]
labels = [f"{r['category']} ({r['share_pct']}%%)" for r in rows]
fig, ax = plt.subplots(figsize=(5, 4))
ax.pie(counts, labels=labels, textprops={"fontsize": 6})
ax.set_title("Timeouts account for 42%% of all API failures", fontsize=8)
fig.savefig("figure.png", dpi=100)
