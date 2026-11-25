"""The fix cycles' progress on figure-bench, drawn with mintfig itself.

Reads runs/r2..r5/results.json (run 1 used the easier, pre-hardening task set and
is left out of the series) and writes progress.png next to this file.

    python evals/figure_bench/make_progress.py
"""

from __future__ import annotations

import json
from pathlib import Path

import mintfig as mint

HERE = Path(__file__).resolve().parent
RUNS = [("r2", "before fixes"), ("r3", "cycle 1"), ("r4", "cycle 2"), ("r5", "cycle 3")]


def _rows(run: str) -> list[dict]:
    return json.loads((HERE / "runs" / run / "results.json").read_text())["tasks_detail"]


def main() -> None:
    labels = [label for _, label in RUNS]
    core, held, extra_core, extra_held = [], [], {}, {}
    for run, label in RUNS:
        rows = _rows(run)
        # Time until the task was over: to the passing submission, or to the last failed one.
        core.append([r["seconds_total"] for r in rows if not r["task"].startswith("h")])
        held.append([r["seconds_total"] for r in rows if r["task"].startswith("h")] or [])
        # Resubmissions: every submission after a task's first (a failed task used all 3).
        extra_core[label] = sum(r["attempts"] - 1 for r in rows if not r["task"].startswith("h"))
        if any(r["task"].startswith("h") for r in rows):
            extra_held[label] = sum(r["attempts"] - 1 for r in rows if r["task"].startswith("h"))

    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs)

    c0, c3 = mean(core[0]), mean(core[-1])
    h1 = mean(held[3])
    fig = mint.explain(
        f"Three fix cycles cut the average time to a clean chat figure by a third, from "
        f"{c0:.0f} s to {c3:.0f} s, and ended resubmissions; held-out tasks take the same "
        f"{h1:.0f} s",
        mint.trend(
            labels,
            points={"benchmark tasks": core, "held-out tasks": held},
            label="Time to a passing figure", unit="s",
            highlight=["benchmark tasks", "held-out tasks"],
            title="Most of the gain came in cycle 1; held-out tasks, added later, match it",
        ),
        mint.compare(
            {label: extra_core[label] + extra_held.get(label, 0) for label in labels},
            sort=False, label="Submissions beyond the first", unit="",
            highlight=labels[0],
            title="Seven resubmissions before the fixes, none after cycle 3",
        ),
        layout=[["a", "a", "b"]],
        subtitle="figure-bench: 10 benchmark tasks per run, plus 5 held-out tasks from run 4; "
                 "fresh agents see only SKILL.md",
        note="Each dot is one task: time from start to its passing submission (or to its last "
             "one, for the one task that failed before the fixes); lines are means. Run 1 "
             "(median 32.5 s) used an easier task set and is not comparable.",
        source="evals/figure_bench/runs/r2–r5/results.json",
        colors={"benchmark tasks": "blue", "held-out tasks": "amber"},
    )
    summary = fig.save(HERE / "progress.png", write_spec=True)
    print(json.dumps({k: summary[k] for k in ("ok", "issues", "display")}, indent=1,
                     ensure_ascii=False))
    for p in summary["panels"]:
        print("--", p["title"])
        for f in p["facts"]:
            print("  ", f)


if __name__ == "__main__":
    main()
