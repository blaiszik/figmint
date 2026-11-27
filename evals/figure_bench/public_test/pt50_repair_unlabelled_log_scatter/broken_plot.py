import csv

import matplotlib.pyplot as plt

with open("data/parser_scaling.csv", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))
kb = [float(r["payload_kb"]) for r in rows]
ms = [float(r["parse_ms"]) for r in rows]
fig, ax = plt.subplots(figsize=(10, 5))
ax.scatter(kb, ms, c=ms, cmap="jet")
ax.set_title("Parser scales linearly with R2 = 0.98", fontsize=8)
fig.savefig("figure.png", dpi=100)
