"""Render the real figures and the real `mint.check` output the demo video shows.

Run from this folder with mintfig's venv: ../../.venv/bin/python make_assets.py
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import mintfig as mint
from mintfig.figcheck import format_report

VARIANTS = ["full model", "no retrieval", "no fine-tuning"]
ACC = [0.82, 0.74, 0.69]
ERR = [0.02, 0.03, 0.03]

# What an agent writes today: wide canvas, truncated axis, a wrong number in the title.
fig, ax = plt.subplots(figsize=(12, 5))
ax.bar(VARIANTS, ACC, yerr=ERR, color=["C0", "C1", "C2"])
ax.set_ylim(0.6, 0.85)
ax.set_title("Removing retrieval costs 12 points of accuracy")
ax.set_ylabel("Test accuracy")
fig.savefig("public/before.png", dpi=150)
before = mint.check(fig, dpi=150)
plt.close(fig)

# After applying the fix hints.
fig, ax = plt.subplots(figsize=(7, 3.6))
ax.bar(VARIANTS, ACC, yerr=ERR, color=["0.35", "#D1495B", "0.65"])
ax.set_title("Removing retrieval costs 8 points of accuracy", loc="left", fontsize=15)
ax.set_ylabel("Test accuracy (95% CI, 5 seeds)", fontsize=11)
ax.tick_params(labelsize=11)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
fig.tight_layout()
fig.savefig("public/after.png", dpi=200)
after = mint.check(fig, dpi=200, bbox_inches=None)
plt.close(fig)

# Or let mintfig draw it.
exp = mint.explain(
    "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
    mint.compare(
        dict(zip(VARIANTS, ACC)),
        error={v: (a - e, a + e) for v, a, e in zip(VARIANTS, ACC, ERR)},
        error_label="95% CI, 5 seeds",
        label="Test accuracy",
        highlight=["no retrieval", "no fine-tuning"],
    ),
    source="runs/ablation (5 seeds per variant)",
)
summary = (
    exp.save("public/mintfig.png", scale=2)
    if "scale" in exp.save.__code__.co_varnames
    else exp.save("public/mintfig.png")
)

out = {
    "before": {
        "ship": before["ship"],
        "report": format_report({**before, "path": "figure.png"}),
        "display": before["display"],
        "numbers": before["claim"]["numbers"],
        "rules": [i["rule"] for i in before["issues"]],
    },
    "after": {
        "ship": after["ship"],
        "report": format_report({**after, "path": "figure.png"}),
        "display": after["display"],
        "numbers": after["claim"]["numbers"],
    },
    "mintfig": {"ship": summary["ship"]},
}
with open("src/assets.json", "w") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)
print(out["before"]["report"])
print()
print(out["after"]["report"])
print(out["mintfig"])
