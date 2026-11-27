"""Real mintchip and mintfig output for the agent-experience video (src/AgentVideo.tsx).

Everything the video shows inside the chat window and the terminal comes from here:
mintchip's HTML chips, popover and table; mintfig's interactive HTML fragment (with its
script removed, since the video drives the hover itself); and the plain-text forms of both.

Run from this folder with mintchip importable, e.g.
    PYTHONPATH=../../../mintchip/src ../../.venv/bin/python make_agent_assets.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import mintchip as mc

import mintfig as mint
from mintfig.interactive import render_html_fragment

HERE = Path(__file__).parent

# The ablation from mintchip's README: four variants, five seeds, 8k steps.
STEPS = list(range(9))
LOSS = {
    "retrieval": [1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42],
    "reranker": [1.86, 1.41, 1.05, 0.83, 0.69, 0.6, 0.55, 0.52, 0.51],
    "warmup": [1.8, 1.52, 1.25, 1.04, 0.9, 0.81, 0.75, 0.72, 0.7],
    "baseline": [1.85, 1.6, 1.36, 1.15, 0.99, 0.89, 0.83, 0.8, 0.78],
}
ROWS = [
    {"variant": "retrieval", "acc": 0.82, "lift": [0.08, 0.05, 0.11], "loss": LOSS["retrieval"]},
    {"variant": "reranker", "acc": 0.79, "lift": [0.05, 0.02, 0.08], "loss": LOSS["reranker"]},
    {"variant": "warmup", "acc": 0.75, "lift": [0.01, -0.02, 0.04], "loss": LOSS["warmup"]},
    {"variant": "baseline", "acc": 0.74, "lift": None, "loss": LOSS["baseline"]},
]

BEFORE = (
    "The ablation finished (5 seeds, 8k steps each). Retrieval did best: validation loss went "
    "from 1.84 to 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43 and finally 0.42, which is inside "
    "the 0.38–0.48 target band, and accuracy reached 0.82, a lift of +0.08 over the baseline "
    "(95% CI +0.05 to +0.11). The reranker reached 0.79 accuracy (+0.05, 95% CI +0.02 to "
    "+0.08) with a final validation loss of 0.51. Warmup reached 0.75 (+0.01, 95% CI −0.02 to "
    "+0.04), so its effect is not distinguishable from zero; its validation loss ended at "
    "0.70. The baseline reached 0.74 accuracy and a final validation loss of 0.78."
)
PROSE = (
    "The ablation finished (5 seeds, 8k steps). Retrieval wins: val loss settled at {loss}, "
    "inside the target band, and accuracy rose by {lift}. Warmup's interval crosses zero, "
    "so drop it."
)
DIRECTIVES = (
    "The ablation finished (5 seeds, 8k steps). Retrieval wins: val loss settled at "
    "{{spark 1.84 1.32 0.96 0.74 0.61 0.52 0.46 0.43 0.42 band=0.38:0.48}}, inside the target "
    "band, and accuracy rose by {{ci 0.08 0.05:0.11 level=0.95}}. Warmup's interval crosses "
    "zero, so drop it."
)
COLUMNS = {
    "variant": "text",
    "acc": {"chip": "num", "header": "accuracy"},
    "lift": {"chip": "ci", "header": "lift, 95% CI", "level": 0.95},
    "loss": {"chip": "spark", "header": "val loss"},
}


def chips() -> dict:
    loss = mc.spark(LOSS["retrieval"], band=(0.38, 0.48))
    lift = mc.ci(0.08, (0.05, 0.11), level=0.95)
    prose_html = mc.format_prose(PROSE, format="html", theme="light", loss=loss, lift=lift)
    prose_text = mc.format_prose(PROSE, loss=loss, lift=lift)
    table = mc.table([dict(r, lift=tuple(r["lift"]) if r["lift"] else None) for r in ROWS], COLUMNS)
    return {
        "css": mc.css(),
        "prose_html": prose_html,
        "prose_text": prose_text,
        "table_html": table.html(theme="light"),
        "table_text": table.text(),
        "directives": DIRECTIVES,
        "numbers_before": len(re.findall(r"[-+−]?\d+(?:\.\d+)?", BEFORE)),
    }


def figure() -> dict:
    fig = mint.explain(
        "Only retrieval gets validation loss under the 0.48 target, from step 6k",
        mint.trend(
            STEPS,
            LOSS,
            x_label="Training step (k)",
            label="Validation loss",
            reference=(0.48, "target 0.48"),
            title="Validation loss, mean of 5 seeds",
        ),
    )
    summary = fig.save(HERE / "public" / "loss.png")
    assert summary["ship"], summary
    frag = render_html_fragment(fig)
    script = re.search(r"<script>.*?</script>", frag, flags=re.DOTALL)
    marks = json.loads(
        re.search(r"var M=(\{.*?\}),SPEC=", script.group(0), flags=re.DOTALL).group(1)
    )
    file = json.loads(re.search(r"FILE=(\"[^\"]*\");", script.group(0)).group(1))
    key = next(k for k, r in marks.items() if r.get("name") == "retrieval" and r.get("x") == "6")
    rec = marks[key]
    # The page script's cite(): FILE · panel · "name @ x = value".
    cite = f"{file} · {rec['panel']} · {rec['name']} @ {rec['x']} = {rec['value']}"
    return {
        "fragment": frag.replace(script.group(0), ""),
        "hover_key": key,
        "cite": cite,
        "caption": summary["deliver"]["caption"],
        "text": fig.to_text(width=72),
    }


def main() -> None:
    out = {"chips": chips(), "figure": figure()}
    with open(HERE / "src" / "agent_assets.json", "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(out["chips"]["prose_text"])
    print(out["chips"]["table_text"])
    print(out["figure"]["text"])
    print("numbers in the before text:", out["chips"]["numbers_before"])
    print("cite:", out["figure"]["cite"], "| caption:", out["figure"]["caption"])


if __name__ == "__main__":
    main()
