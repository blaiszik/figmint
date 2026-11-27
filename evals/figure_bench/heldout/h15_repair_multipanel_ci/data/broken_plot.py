"""Draft 2-panel training curve (unlabelled bands, overlapping text, wrong crossing epoch)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "h15_broken.png"

by_model: dict[str, list[dict[str, float]]] = {}
with open(DATA_DIR / "training.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        by_model.setdefault(row["model"], []).append(
            {
                "epoch": float(row["epoch"]),
                "loss": float(row["val_loss_mean"]),
                "loss_sd": float(row["val_loss_sd"]),
                "acc": float(row["val_acc_mean"]),
                "acc_sd": float(row["val_acc_sd"]),
            }
        )

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.4), dpi=100)
colors = {"baseline_sgd": "#64748b", "cosine_warmup": "#2563eb"}

for name, pts in by_model.items():
    ep = np.array([p["epoch"] for p in pts])
    loss = np.array([p["loss"] for p in pts])
    lsd = np.array([p["loss_sd"] for p in pts])
    acc = np.array([p["acc"] for p in pts])
    asd = np.array([p["acc_sd"] for p in pts])

    ax1.plot(ep, loss, color=colors[name], lw=2, label=name)
    ax1.fill_between(ep, loss - lsd, loss + lsd, color=colors[name], alpha=0.2)
    ax2.plot(ep, acc, color=colors[name], lw=2, label=name)
    ax2.fill_between(ep, acc - asd, acc + asd, color=colors[name], alpha=0.2)

ax1.set_xlabel("Epoch")
ax1.set_ylabel("Validation loss")
ax1.legend(loc="upper right")
ax1.text(17.5, 1.08, "Warmup starts slower", fontsize=11)
ax1.text(17.5, 1.05, "Then overtakes later", fontsize=11)

ax2.set_xlabel("Epoch")
ax2.set_ylabel("Validation accuracy (%)")
ax2.legend(loc="lower right")

fig.suptitle("Cosine warmup overtakes baseline at epoch 42", fontsize=13)
fig.tight_layout()
fig.savefig(OUT_PATH, dpi=100)
