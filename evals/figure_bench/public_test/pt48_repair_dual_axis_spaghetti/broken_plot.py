import csv

import matplotlib.pyplot as plt

with open("data/cluster_14d.csv", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))
day = [int(r["day"]) for r in rows]
cpu = [float(r["cpu_pct"]) for r in rows]
mem = [float(r["mem_pct"]) for r in rows]
err = [float(r["error_rate_pct"]) for r in rows]
fig, ax1 = plt.subplots(figsize=(11, 4.5))
ax1.plot(day, cpu, "r-", label="CPU %")
ax1.plot(day, mem, "g-", label="Memory %")
ax2 = ax1.twinx()
ax2.plot(day, err, "b--", label="Errors %")
ax1.legend(loc="center")
ax1.text(9.2, 82, "Peak error 9.2% on Day 10 (-4.1% drop)")
ax1.set_title("Cluster health: peak error 9.2%% on Day 10", fontsize=8)
fig.savefig("figure.png", dpi=100)
